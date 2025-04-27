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
logging.basicConfig(level=logging.INFO)

def setup(base_url=None, skip_ws=False):
    print("Connecting account...")
    account: LocalAccount = eth_account.Account.from_key("")  # 🔐 your private key
    address = ""  # your address

    if address == "":
        address = account.address

    print(f"Running with address: {address}")
    info = Info(base_url, skip_ws)
    spot_user_state = info.spot_user_state(address)
    print(f"Spot balances: {spot_user_state['balances']}")

    if not any(float(b['total']) > 0 for b in spot_user_state["balances"]):
        raise Exception("No spot balance found.")

    exchange = Exchange(account, base_url, account_address=address)
    return address, info, exchange

class GridTrading:
    def __init__(self, address, info, exchange, COIN, gridnum, gridmax, gridmin, tp, eachgridamount, hasspot=False):
        self.address = address
        self.info = info
        self.exchange = exchange
        self.COIN = COIN
        self.symbol = f"{COIN}/USDC"
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
        print(f"Grid levels: {self.eachprice}")

        try:
            midprice = float(self.info.all_mids()[self.COIN])
        except Exception as e:
            logger.error(f"Error fetching midprice: {e}")
            return

        print(f"Midprice: {midprice}")

        for i, price in enumerate(self.eachprice):
            if price > midprice:
                self.buy_orders.append({"index": i, "oid": 0, "activated": False})
                continue

            order_result = self.exchange.order(self.symbol, True, self.eachgridamount, price, {"limit": {"tif": "Gtc"}})

            if order_result.get("status") == "ok":
                statuses = order_result["response"]["data"].get("statuses", [])
                for status in statuses:
                    if "error" in status:
                        logger.warning(f"Error placing buy order: {status['error']}")
                        break
                else:
                    oid = statuses[0].get("resting", {}).get("oid", 0)
                    print(f"✅ Buy order placed at {price}, oid: {oid}")
                    self.buy_orders.append({"index": i, "oid": oid, "activated": True})
            else:
                logger.error(f"❌ Buy order failed: {order_result}")

    def check_orders(self):
        # Check buy orders
        for buy_order in self.buy_orders[:]:
            if buy_order["activated"]:
                order_status = self.info.query_order_by_oid(self.address, buy_order["oid"])
                order_data = order_status.get("order", {})
                if order_data.get("status") == "filled":
                    sell_price = round(self.eachprice[buy_order["index"]] + self.tp, 6)
                    sell_result = self.exchange.order(self.symbol, False, self.eachgridamount, sell_price, {"limit": {"tif": "Gtc"}})

                    if sell_result.get("status") == "ok":
                        statuses = sell_result["response"]["data"].get("statuses", [])
                        oid = statuses[0].get("resting", {}).get("oid", 0)
                        print(f"✅ Sell order placed at {sell_price}, oid: {oid}")
                        self.sell_orders.append({"index": buy_order["index"], "oid": oid, "activated": True})
                        self.buy_orders.remove(buy_order)
                    else:
                        logger.error(f"❌ Sell order failed: {sell_result}")

        # Check sell orders
        for sell_order in self.sell_orders[:]:
            if sell_order["activated"]:
                order_status = self.info.query_order_by_oid(self.address, sell_order["oid"])
                order_data = order_status.get("order", {})
                if order_data.get("status") == "filled":
                    buy_price = self.eachprice[sell_order["index"]]
                    buy_result = self.exchange.order(self.symbol, True, self.eachgridamount, buy_price, {"limit": {"tif": "Gtc"}})

                    if buy_result.get("status") == "ok":
                        statuses = buy_result["response"]["data"].get("statuses", [])
                        oid = statuses[0].get("resting", {}).get("oid", 0)
                        print(f"🔁 Buy order re-placed at {buy_price}, oid: {oid}")
                        self.buy_orders.append({"index": sell_order["index"], "oid": oid, "activated": True})
                        self.sell_orders.remove(sell_order)
                    else:
                        logger.error(f"❌ Re-buy order failed: {buy_result}")

    def trader(self):
        self.check_orders()

def main():
    address, info, exchange = setup(base_url=constants.MAINNET_API_URL, skip_ws=True)

    user_state = info.user_state(address)
    positions = user_state.get("assetPositions", [])
    if positions:
        print("Open positions:")
        for position in positions:
            print(json.dumps(position["position"], indent=2))
    else:
        print("No open positions.")

    trading = GridTrading(
        address, info, exchange,
        COIN="HYPE",  # change this to your desired coin
        gridnum=10,
        gridmax=18.10,
        gridmin=17.35,
        tp=0.2,
        eachgridamount=0.6,
        hasspot=True
    )

    trading.compute()
    while True:
        trading.trader()
        time.sleep(2)

if __name__ == "__main__":
    main()
