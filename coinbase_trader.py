import os
import time
import pandas as pd
import numpy as np
from datetime import datetime
import cbpro
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filename='trading_bot.log')
logger = logging.getLogger('coinbase_trader')

# Load environment variables from .env file
load_dotenv()

# Coinbase API credentials - store these in a .env file, not in the script
API_KEY = os.getenv('COINBASE_API_KEY')
API_SECRET = os.getenv('COINBASE_API_SECRET')
API_PASSPHRASE = os.getenv('COINBASE_PASSPHRASE')

# Trading parameters
ETH_SYMBOL = 'ETH-EUR'
BTC_SYMBOL = 'BTC-EUR'
CHECK_INTERVAL = 3600  # Check market every hour
MOVING_AVG_SHORT = 12  # 12-hour moving average
MOVING_AVG_LONG = 26   # 26-hour moving average

class CoinbaseTrader:
    def __init__(self):
        self.client = cbpro.AuthenticatedClient(API_KEY, API_SECRET, API_PASSPHRASE)
        self.price_history = {
            'ETH-EUR': [],
            'BTC-EUR': []
        }
        logger.info("Trading bot initialized")
        
    def get_account_balances(self):
        """Get account balances for EUR, ETH, and BTC"""
        accounts = self.client.get_accounts()
        balances = {}
        
        for account in accounts:
            if account['currency'] in ['EUR', 'ETH', 'BTC']:
                balances[account['currency']] = {
                    'balance': float(account['balance']),
                    'available': float(account['available']),
                    'id': account['id']
                }
                
        logger.info(f"Current balances: {balances}")
        return balances
        
    def get_current_prices(self):
        """Get current prices for ETH and BTC"""
        eth_ticker = self.client.get_product_ticker(product_id=ETH_SYMBOL)
        btc_ticker = self.client.get_product_ticker(product_id=BTC_SYMBOL)
        
        current_prices = {
            'ETH-EUR': float(eth_ticker['price']),
            'BTC-EUR': float(btc_ticker['price'])
        }
        
        # Update price history
        timestamp = datetime.now()
        self.price_history['ETH-EUR'].append((timestamp, current_prices['ETH-EUR']))
        self.price_history['BTC-EUR'].append((timestamp, current_prices['BTC-EUR']))
        
        # Keep only recent price history
        max_history = max(MOVING_AVG_SHORT, MOVING_AVG_LONG) + 5
        if len(self.price_history['ETH-EUR']) > max_history:
            self.price_history['ETH-EUR'] = self.price_history['ETH-EUR'][-max_history:]
            self.price_history['BTC-EUR'] = self.price_history['BTC-EUR'][-max_history:]
            
        logger.info(f"Current prices: {current_prices}")
        return current_prices
    
    def analyze_market(self):
        """Analyze market using moving averages crossover strategy"""
        if len(self.price_history['ETH-EUR']) < MOVING_AVG_LONG:
            logger.info("Not enough price history for analysis")
            return None
            
        # Extract ETH prices
        eth_prices = [price for _, price in self.price_history['ETH-EUR']]
        
        # Calculate moving averages
        short_ma = sum(eth_prices[-MOVING_AVG_SHORT:]) / MOVING_AVG_SHORT
        long_ma = sum(eth_prices[-MOVING_AVG_LONG:]) / MOVING_AVG_LONG
        
        # Simple moving average crossover strategy
        if short_ma > long_ma:
            signal = 'BUY'
        elif short_ma < long_ma:
            signal = 'SELL'
        else:
            signal = 'HOLD'
            
        logger.info(f"Market analysis: {signal} (Short MA: {short_ma}, Long MA: {long_ma})")
        return {
            'signal': signal,
            'short_ma': short_ma,
            'long_ma': long_ma,
            'current_price': eth_prices[-1]
        }
    
    def execute_trade(self, signal):
        """Execute trade based on signal and available balances"""
        balances = self.get_account_balances()
        
        if signal == 'BUY' and balances.get('EUR', {}).get('available', 0) > 10:
            # Buy ETH with 90% of available EUR
            eur_to_use = balances['EUR']['available'] * 0.9
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
                
        elif signal == 'SELL' and balances.get('ETH', {}).get('available', 0) > 0.01:
            # Sell 90% of available ETH
            eth_to_sell = balances['ETH']['available'] * 0.9
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

    def run_trading_cycle(self):
        """Run one full trading cycle"""
        try:
            # Get current market data
            self.get_current_prices()
            
            # Analyze the market
            analysis = self.analyze_market()
            
            # Execute trade if we have enough data for analysis
            if analysis:
                self.execute_trade(analysis['signal'])
                
        except Exception as e:
            logger.error(f"Error in trading cycle: {e}")

def main():
    """Main function to run the trading bot"""
    trader = CoinbaseTrader()
    
    logger.info("Starting trading bot")
    print("Trading bot started. Press Ctrl+C to stop.")
    
    try:
        while True:
            trader.run_trading_cycle()
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Trading bot stopped by user")
        print("Trading bot stopped.")

if __name__ == "__main__":
    main()