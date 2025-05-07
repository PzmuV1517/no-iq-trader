"""
This module implements a trading bot that uses a moving average crossover strategy 
to trade Ethereum (ETH) against Euro (EUR) on the Coinbase Pro exchange.

The bot periodically checks the market, analyzes the price history, 
and executes buy/sell orders based on the analysis.
"""

import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import cbpro
from dotenv import load_dotenv

# --- Configuration ---
# Load environment variables from .env file.
load_dotenv()

# Coinbase API credentials.
API_KEY = os.getenv('COINBASE_API_KEY')
API_SECRET = os.getenv('COINBASE_API_SECRET')
API_PASSPHRASE = os.getenv('COINBASE_PASSPHRASE')

# Trading parameters.
ETH_SYMBOL = 'ETH-EUR'
BTC_SYMBOL = 'BTC-EUR'
CHECK_INTERVAL = 3600  # Check the market every hour.
MOVING_AVG_SHORT = 12  # 12-hour short moving average.
MOVING_AVG_LONG = 26  # 26-hour long moving average.
MIN_EUR_TRADE = 10  # Minimum EUR amount for a trade.
MIN_ETH_TRADE = 0.01  # Minimum ETH amount for a trade.
TRADE_PERCENTAGE = 0.9 # Percentage of balance to trade

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='trading_bot.log'
)
logger = logging.getLogger('coinbase_trader')


class CoinbaseTrader:
    """
    A class for interacting with the Coinbase Pro API and executing trades.
    """
    def __init__(self) -> None:
        """
        Initializes the CoinbaseTrader with API credentials and sets up the price history.
        """
        if not all([API_KEY, API_SECRET, API_PASSPHRASE]):
            logger.error("Missing Coinbase API credentials. Please check your .env file.")
            raise ValueError("Missing Coinbase API credentials.")

        self.client = cbpro.AuthenticatedClient(API_KEY, API_SECRET, API_PASSPHRASE)
        self.price_history = {
            'ETH-EUR': [],
            'BTC-EUR': []  # Keeping BTC history although not used in current strategy.
        }
        logger.info("Trading bot initialized")

    def get_account_balances(self) -> Dict[str, Dict[str, float]]:
        """
        Retrieves account balances for EUR, ETH, and BTC from Coinbase Pro.
        
        Returns:
            Dict[str, Dict[str, float]]: A dictionary containing balances for EUR, ETH, and BTC.
        """
        accounts = self.client.get_accounts()
        balances = {}
        
        for account in accounts:
            if account['currency'] in ['EUR', 'ETH', 'BTC']:
                balances[account['currency']] = {
                    'balance': float(account['balance']),
                    'available': float(account['available']), # Available balance for trade.
                    'id': account['id']  # Keeping the account ID for debugging if needed.
                }
                
        logger.info(f"Current balances: {balances}")
        return balances

    def get_current_prices(self) -> Dict[str, float]:
        """
        Retrieves the current market prices for ETH-EUR and BTC-EUR from Coinbase Pro.
        Updates the price history with the new prices.

        Returns:
            Dict[str, float]: A dictionary containing the current prices for ETH-EUR and BTC-EUR.
        """
        eth_ticker = self.client.get_product_ticker(product_id=ETH_SYMBOL)
        btc_ticker = self.client.get_product_ticker(product_id=BTC_SYMBOL)
        
        current_prices = {
            'ETH-EUR': float(eth_ticker['price']),
            'BTC-EUR': float(btc_ticker['price'])
        }
        
        # Update price history.
        timestamp = datetime.now()
        self.price_history['ETH-EUR'].append((timestamp, current_prices['ETH-EUR']))
        self.price_history['BTC-EUR'].append((timestamp, current_prices['BTC-EUR']))
        
        # Keep only recent price history, delete old data.
        max_history = max(MOVING_AVG_SHORT, MOVING_AVG_LONG) + 5
        if len(self.price_history['ETH-EUR']) > max_history:
            self.price_history['ETH-EUR'] = self.price_history['ETH-EUR'][-max_history:]
            self.price_history['BTC-EUR'] = self.price_history['BTC-EUR'][-max_history:]
            
        logger.info(f"Current prices: {current_prices}")
        return current_prices

    def analyze_market(self) -> Optional[Dict[str, float]]:
        """
        Analyzes the market using a moving averages crossover strategy for ETH-EUR.

        Returns:
            Optional[Dict[str, float]]: A dictionary containing the analysis results 
                                        (signal, short MA, long MA, current price),
                                        or None if not enough data is available.
        """
        if len(self.price_history['ETH-EUR']) < MOVING_AVG_LONG:
            logger.info("Not enough price history for analysis")
            return None
            
        # Extract ETH prices.
        eth_prices = [price for _, price in self.price_history['ETH-EUR']]
        
        # Calculate moving averages.
        short_ma = sum(eth_prices[-MOVING_AVG_SHORT:]) / MOVING_AVG_SHORT
        long_ma = sum(eth_prices[-MOVING_AVG_LONG:]) / MOVING_AVG_LONG
        
        # Simple moving average crossover strategy.
        if short_ma > long_ma:
            signal = 'BUY'
        elif short_ma < long_ma:
            signal = 'SELL'
        else:
            signal = 'HOLD'

        logger.info(f"Market analysis: {signal} (Short MA: {short_ma:.2f}, Long MA: {long_ma:.2f})")
        return {
            'signal': signal,
            'short_ma': short_ma,
            'long_ma': long_ma,
            'current_price': eth_prices[-1]
        }

    def execute_trade(self, signal: str) -> Optional[Dict]:
        """
        Executes a trade based on the given signal and available balances.

        Args:
            signal (str): The trading signal ('BUY', 'SELL', or 'HOLD').

        Returns:
            Optional[Dict]: The order details if a trade was executed, None otherwise.
        """
        balances = self.get_account_balances()
        
        if signal == 'BUY' and balances.get('EUR', {}).get('available', 0) > MIN_EUR_TRADE:
            # Buy ETH with a percentage of available EUR.
            eur_to_use = balances['EUR']['available'] * TRADE_PERCENTAGE
            logger.info(f"Placing buy order for ETH using {eur_to_use} EUR")
            
            try:
                order = self.client.place_market_order(
                    product_id=ETH_SYMBOL,
                    side='buy',
                    funds=str(eur_to_use)
                )
                logger.info(f"Buy order placed: {order}")
                return order
            except Exception as e:
                logger.error(f"Error placing buy order: {e}")
                
        elif signal == 'SELL' and balances.get('ETH', {}).get('available', 0) > MIN_ETH_TRADE:
            # Sell a percentage of available ETH.
            eth_to_sell = balances['ETH']['available'] * TRADE_PERCENTAGE
            logger.info(f"Placing sell order for {eth_to_sell} ETH")
            
            try:
                order = self.client.place_market_order(
                    product_id=ETH_SYMBOL,
                    side='sell',
                    size=str(eth_to_sell)
                )
                logger.info(f"Sell order placed: {order}")
                return order
            except Exception as e:
                logger.error(f"Error placing sell order: {e}")
                
        else:
            logger.info("No trade executed: insufficient funds or HOLD signal")
            return None

    def can_trade(self) -> bool:
        """
        Checks if the bot has enough funds to execute a trade.

        Returns:
            bool: True if the bot can trade, False otherwise.
        """
        balances = self.get_account_balances()
        eur_available = balances.get('EUR', {}).get('available', 0)
        eth_available = balances.get('ETH', {}).get('available', 0)
        return eur_available > MIN_EUR_TRADE or eth_available > MIN_ETH_TRADE

    def run_trading_cycle(self) -> None:
        """
        Runs one full trading cycle: gets current prices, analyzes the market,
        and executes a trade if applicable.
        """
        try:
            # Get current market data.
            self.get_current_prices()
            
            # Analyze the market.
            analysis = self.analyze_market()
            
            # Execute trade if we have enough data for analysis and the bot can trade.
            if analysis and self.can_trade():
                self.execute_trade(analysis['signal'])
                
        except Exception as e:
            logger.error(f"Error in trading cycle: {e}")

def main() -> None:
    """
    Main function to run the trading bot.
    Handles the bot's trading cycle and error handling.
    """
    trader = CoinbaseTrader()
    
    logger.info("Starting trading bot")
    print("Trading bot started. Press Ctrl+C to stop.")
    
    try:
        while True: 
             trader.run_trading_cycle()
             time.sleep(CHECK_INTERVAL)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        logger.info("The bot will continue working.")
    except KeyboardInterrupt:
        logger.info("Trading bot stopped by user")
        print("Trading bot stopped.")

if __name__ == "__main__":
    main()