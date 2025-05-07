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
from typing import Dict, List, Optional, Tuple, Any
import platform

import pygame

# import pygame only if it is windows
if platform.system() == 'Windows':
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
TRADE_PERCENTAGE = 0.9  # Percentage of balance to trade

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='trading_bot.log'
)
logger = logging.getLogger('coinbase_trader')

# --- Pygame Constants ---
if platform.system() == 'Windows':
    # Window settings.
    WINDOW_WIDTH = 800
    WINDOW_HEIGHT = 600

    # Colors.
    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)
    GREEN = (0, 255, 0)
    RED = (255, 0, 0)
    BLUE = (0, 0, 255)
    YELLOW = (255, 255, 0)

    # Graph constants.
    GRAPH_WIDTH = 600
    GRAPH_HEIGHT = 200
    GRAPH_X = 100
    GRAPH_Y = 350
    NUM_PRICE_POINTS = 10  # Number of price points to display (10 hours).

    class PygameWindow:
        """
        A class to manage the Pygame graphical window for the trading bot.
        """
        def __init__(self) -> None:
            """
            Initializes the Pygame window.
            """
            pygame.init()
            self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
            pygame.display.set_caption("Coinbase Trader Bot")
            self.font = pygame.font.Font(None, 30)

        def draw_text(self, text: str, color: Tuple[int, int, int], x: int, y: int) -> None:
            """
            Draws text on the screen.

            Args:
                text (str): The text to draw.
                color (Tuple[int, int, int]): The color of the text.
                x (int): The x-coordinate.
                y (int): The y-coordinate.
            """
            text_surface = self.font.render(text, True, color)
            text_rect = text_surface.get_rect()
            text_rect.topleft = (x, y)
            self.screen.blit(text_surface, text_rect)

        def draw_graph(self, prices: List[float], max_price: float, min_price: float) -> None:
            """
            Draws a simple graph of ETH-EUR price history using rectangles.

            Args:
                prices (List[float]): The list of ETH-EUR prices.
                max_price (float): The maximum price in the history.
                min_price (float): The minimum price in the history.
            """
            if not prices:
                return

            price_range = max_price - min_price
            bar_width = GRAPH_WIDTH / len(prices)

            for i, price in enumerate(prices):
                if price_range == 0:
                    bar_height = GRAPH_HEIGHT // 2  # Avoid division by zero
                else:
                    bar_height = int((price - min_price) / price_range * GRAPH_HEIGHT)

                bar_x = GRAPH_X + i * bar_width
                bar_y = GRAPH_Y + GRAPH_HEIGHT - bar_height

                pygame.draw.rect(self.screen, BLUE, (bar_x, bar_y, bar_width, bar_height))

        def update_display(self, current_prices: Dict[str, float], balances: Dict[str, Dict[str, float]], analysis: Dict[str, Any], total_profit_loss: float, eth_prices:List[float], max_price: float, min_price: float) -> None:
            """
            Updates the display with current market data, balances, signal, profit/loss, and graph.
            """
            self.screen.fill(BLACK)
            self.draw_text(f"ETH-EUR Price: {current_prices['ETH-EUR']:.2f}", WHITE, 50, 50)
            self.draw_text(f"EUR Balance: {balances.get('EUR', {}).get('balance', 0):.2f}", GREEN, 50, 100)
            self.draw_text(f"ETH Balance: {balances.get('ETH', {}).get('balance', 0):.4f}", GREEN, 50, 150)
            self.draw_text(f"Signal: {analysis['signal']}", RED if analysis['signal'] == 'SELL' else GREEN if analysis['signal'] == 'BUY' else YELLOW, 50, 200)
            self.draw_text(f"Total Profit/Loss: {total_profit_loss:.2f}", WHITE, 50, 250)
            self.draw_graph(eth_prices, max_price, min_price)
            pygame.display.flip()

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
        self.total_profit_loss = 0.0  # Initialize total profit/loss.
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
                    'available': float(account['available']),  # Available balance for trade.
                    'id': account['id']  # Keep the account ID for debug.
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
        max_history = max(MOVING_AVG_SHORT, MOVING_AVG_LONG) + 5  # Keep a little more to avoid issues.
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

        # Simple moving average cross over strategy.
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

            try:  # Try to make the trade.
                order = self.client.place_market_order(
                    product_id=ETH_SYMBOL,
                    side='buy',
                    funds=str(eur_to_use)
                )
                logger.info(f"Buy order placed: {order}")
                return order
                current_price = self.get_current_prices()['ETH-EUR']
                # Calculate profit/loss.
                eth_bought = eur_to_use / current_price
                self.total_profit_loss -= eur_to_use  # Subtract the money spent.
            except Exception as e:  # if any error occurs.
                logger.error(f"Error placing buy order: {e}")

        elif signal == 'SELL' and balances.get('ETH', {}).get('available', 0) > MIN_ETH_TRADE:
            # Sell a percentage of available ETH.
            eth_to_sell = balances['ETH']['available'] * TRADE_PERCENTAGE
            logger.info(f"Placing sell order for {eth_to_sell} ETH")

            try:  # Try to make the trade.
                order = self.client.place_market_order(
                    product_id=ETH_SYMBOL,
                    side='sell',
                    size=str(eth_to_sell)
                )
                logger.info(f"Sell order placed: {order}")
                current_price = self.get_current_prices()['ETH-EUR']
                # Calculate profit/loss.
                eur_received = eth_to_sell * current_price
                self.total_profit_loss += eur_received
                return order
            except Exception as e:  # if any error occurs.
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
            current_prices = self.get_current_prices()

            # Get balances.
            balances = self.get_account_balances()
            eur_balance = balances.get('EUR', {}).get('balance', 0)
            eth_balance = balances.get('ETH', {}).get('balance', 0)

            # Get the last 10 hours
            eth_prices = [price for _, price in self.price_history['ETH-EUR'][-NUM_PRICE_POINTS:]]

            # Calculate the maximum and minimum prices in the last 10 hours.
            max_price = max(eth_prices) if eth_prices else 0
            min_price = min(eth_prices) if eth_prices else 0

            # Analyze the market.
            analysis = self.analyze_market()

            # Execute trade if we have enough data for analysis and the bot can trade.
            if analysis and self.can_trade():
                self.execute_trade(analysis['signal'])
            
            if platform.system() == 'Windows':
                # Update the pygame window
                pygame_window.update_display(
                    current_prices,
                    balances,
                    analysis,
                    self.total_profit_loss,
                    eth_prices,
                    max_price,
                    min_price
                )
            else:
                # Display market data.
                print(f"-----------------------------------------")
                print(f"|     Current Market Data  - {datetime.now()}      |")
                print(f"-----------------------------------------")
                print(f"| ETH-EUR Price: {current_prices['ETH-EUR']:<15.2f} |")
                print(f"| EUR Balance: {eur_balance:<17.2f} |")
                print(f"| ETH Balance: {eth_balance:<17.4f} |")
                print(f"| Signal: {analysis['signal']:<21} |")
                print(f"| Total Profit/Loss: {self.total_profit_loss:<13.2f} |")

        except Exception as e:
            logger.error(f"Error in trading cycle: {e}")

def main() -> None:
    """
    Main function to run the trading bot.
    Handles the bot's trading cycle and error handling.
    """

    # initialize pygame window if it is windows.
    if platform.system() == 'Windows':
        global pygame_window
        pygame_window = PygameWindow()

    trader = CoinbaseTrader()
    
    
    logger.info("Starting trading bot")
    print("Trading bot started. Press Ctrl+C to stop.")

    try:  # Try to keep the bot working.
        while True:
            trader.run_trading_cycle()  # Execute one trading cycle.          
            if platform.system() == 'Windows':
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
            time.sleep(CHECK_INTERVAL)  # wait
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        logger.info("The bot will continue working.")
    except KeyboardInterrupt:
        logger.info("Trading bot stopped by user")
        print("Trading bot stopped.")

if __name__ == "__main__":
    main()