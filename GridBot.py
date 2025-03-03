import json
import os
import logging
import eth_account
import time
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

logger = logging.getLogger(__name__)

def setup(base_url=None, skip_ws=False):
    print("Connect account...")
    # API_KEY
    account: LocalAccount = eth_account.Account.from_key("")
    # Wallet Address if it's correct address it should show your current balance
    address = ""
    if address == "":
        address = account.address
    print("Running with account address:", address)

    if address != account.address:
        print("Running with agent address:", account.address)
    info = Info(base_url, skip_ws)
    # user_state = info.user_state(address)
    spot_user_state = info.spot_user_state(address)
    print('spot_user_state: ', spot_user_state)

    for spot_data in spot_user_state["balances"]:
      if spot_data['total'] != '0':
          print(f"Coin: {spot_data['coin']}, Total: {spot_data['total']}")
      else:
          error_string = f"No account value found on spot."
          raise Exception(error_string)

    exchange = Exchange(account, base_url, account_address=address)
    return address, info, exchange

# Thanks to @timebaseline for grid bot strategy
class GridTrading:
    def __init__(self, address, info, exchange, COIN, gridnum, gridmax, gridmin, tp, eachgridamount, hasspot=False):
        self.address = address
        self.info = info
        self.exchange = exchange
        self.COIN = COIN
        self.gridnum = gridnum
        self.gridmax = gridmax
        self.gridmin = gridmin
        self.tp = tp
        self.eachgridamount = eachgridamount
        self.hasspot = hasspot
        self.eachprice = []
        self.buy_orders = []
        self.sell_orders = []

    def compute(self):
        pricestep = (self.gridmax - self.gridmin) / self.gridnum
        self.eachprice = [round(self.gridmin + i * pricestep, 6) for i in range(self.gridnum)]
        logger.info(f"Each grid's price: {self.eachprice}")

        midprice = float(self.info.all_mids()[self.COIN][:-1])
        print('Midprice: ', midprice)
        print('Grid price: ', self.eachprice)
        print('coin: ', self.COIN)
        for i, price in enumerate(self.eachprice):
            if price > midprice:
                self.buy_orders.append({"index": i, "oid": 0, "activated": False})
                continue
            order_result = self.exchange.order(self.COIN, True, self.eachgridamount, price, {"limit": {"tif": "Gtc"}})

            if order_result.get("status") == "ok":
              # Check if there is an error in the statuses
              statuses = order_result["response"]["data"].get("statuses", [])
              
              # Loop through the statuses and check for an error
              error_found = False
              for status in statuses:
                  if 'error' in status:
                      print(f"Error: {status['error']}")
                      error_found = True
                      break  # Stop checking once an error is found

              if not error_found:
                  # If no error found, proceed with the normal order processing
                  print(f"Open order buy price: {midprice}, status: {order_result.get('status')}")
                  buy_oid = order_result["response"]["data"]["statuses"][0].get("resting", {}).get("oid", 0)
                  self.buy_orders.append({"index": i, "oid": buy_oid, "activated": True})
              else:
                  # If an error was found, you can handle it differently or skip this order
                  print("Order could not be processed due to the error.")

    def check_orders(self):
        for buy_order in self.buy_orders[:]:
            if buy_order["activated"]:
                order_status = self.info.query_order_by_oid(self.address, buy_order["oid"])
                if order_status.get("order", {}).get("status") == "filled":
                    sell_price = self.eachprice[buy_order["index"]] + self.tp
                    sell_order_result = self.exchange.order(self.COIN, False, self.eachgridamount, sell_price, {"limit": {"tif": "Gtc"}})
                    if sell_order_result.get("status") == "ok":
                        print(f"Open order sell price: {sell_price}, status: {sell_order_result.get('status')}")
                        sell_oid = sell_order_result["response"]["data"]["statuses"][0].get("resting", {}).get("oid", 0)
                        self.sell_orders.append({"index": buy_order["index"], "oid": sell_oid, "activated": True})
                        self.buy_orders.remove(buy_order)

    def trader(self):
        self.check_orders()

def main():
    # mainnet api config
    address, info, exchange = setup(base_url=constants.MAINNET_API_URL, skip_ws=True)
    
    # testnet api config
    # address, info, exchange = setup(constants.TESTNET_API_URL, skip_ws=True)
    
    # Get the user state and print out position information
    user_state = info.user_state(address)
    positions = []
    for position in user_state["assetPositions"]:
        positions.append(position["position"])
    if len(positions) > 0:
        print("positions:")
        for position in positions:
            print(json.dumps(position, indent=2))
    else:
        print("no open positions")

    # change token name, total grid step, grid max price length, grid min price length, tp price from position, size based on token not usdc
    trading = GridTrading(address, info, exchange, "HYPE", 10, 21.2, 18.5, 0.01, 0.7, hasspot=False)
    trading.compute()
    while True:
        trading.trader()
        time.sleep(1)

if __name__ == "__main__":
    main()
