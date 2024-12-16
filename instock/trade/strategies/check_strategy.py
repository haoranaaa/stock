#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime
import os.path
import datetime as dt
import random
from typing import List, Tuple
import instock.lib.trade_time as trd
from instock.core.realtime import real_sanpshot
from dateutil import tz

from instock.lib.trade_time import get_previous_trade_date, get_next_trade_date
from instock.trade.robot.infrastructure.default_handler import DefaultLogHandler
from instock.trade.robot.infrastructure.strategy_template import StrategyTemplate
import instock.lib.database as mdb
import pandas as pd
import instock.core.tablestructure as tbs

class Strategy(StrategyTemplate):
    cash_limit = 10000

    def init(self):
        minute_interval = 5
        self.clock_engine.register_interval(minute_interval, trading=False)

    def buy_strategy(self):
        balance = pd.DataFrame([self.user.balance])
        if balance.empty:
            return
        cash = self.user.balance['可用金额']
        if cash < self.cash_limit:
            self.log.info(f'可用金额不足 {self.cash_limit}, 不发起买入操作')
            return
        prepare_buy = self.get_stocks_to_buy()
        if not prepare_buy or len(prepare_buy) < 1:
            return

        for code, price, amount in prepare_buy:
            try:
                self.user.buy(code, price=price, amount=amount)
            except Exception as e:
                self.log.info(f'买入已委托： {code} 价格：{price}, 数量：{amount}, 总价格：{price * amount}, message:{e}')
                pass

    def get_stocks_to_buy(self) -> List[Tuple[str, float, int]]:

        date_str = trd.get_trade_date_last()

        fetch = mdb.executeSqlFetch(
            f"SELECT * FROM `{tbs.TABLE_CN_STOCK_BUY_DATA['name']}` WHERE `date`='{date_str}'")
        pd_result = pd.DataFrame(fetch, columns=list(tbs.TABLE_CN_STOCK_BUY_DATA['columns']))
        
        if pd_result.empty:
            return []

        random_row = pd_result.sample(n=1)
        price = real_sanpshot.get_real_time_quote(random_row['code'].values[0])
        if not price:
           self.log.info(f'获取实时报价失败 {random_row} price is none!')
           return []
        cash = self.user.balance['可用金额']
        amount = int((cash / 2 / price) // 100) * 100
        return [(random_row['code'].values[0], float(price), amount)]

    def check_orders(self):
        #校验委托订单是否已经成交
        for order in self.user.today_entrusts:
            # {"message": "msg"}
            if order.get('备注') == "已成交":
                continue
            order_no = order.get("合同编号", "").strip('="')
            # self.user.cancel_entrust(order_no)
            if order.get("操作") == "买入":
                pass
            elif order.get("操作") == "卖出":
                pass

    def get_stocks_to_sell(self) -> List[Tuple[str, float, int]]:

        date_str = trd.get_trade_date_last()

        tb = tbs.TABLE_CN_STOCK_SELL_DATA
        if not mdb.checkTableIsExist(tb):
            return []
        fetch = mdb.executeSqlFetch(
            f"SELECT * FROM `{tb['name']}` WHERE `date`='{date_str}'")
        pd_result = pd.DataFrame(fetch, columns=list(tbs.TABLE_CN_STOCK_BUY_DATA['columns']))

        if pd_result.empty:
            return []
        positions = self.user.positions
        frame = pd.DataFrame(positions)
        if frame.empty:
            return []
        result = []
        for ps in frame.values:
            amount = ps['可用余额']
            for value in pd_result.values:
                if (ps['证券代码'].strip('="')) == value['code']:
                    price = real_sanpshot.get_real_time_quote(value['code'])
                    if price is None:
                        price = value['open']
                    result.append([value['code'], price, amount])
        return result

    def sell_strategy(self):
        balance = pd.DataFrame([self.user.balance])
        if balance.empty:
            return
        prepare_buy = self.get_stocks_to_sell()
        if not prepare_buy or len(prepare_buy) < 1:
            return

        for code, price, amount in prepare_buy:
            try:
                self.user.sell(code, price=price, amount=amount)
            except Exception as e:
                self.log.info(f'卖出已委托： {code} 价格：{price}, 数量：{amount}, 总价格：{price * amount}, message:{e}')
                pass



    def clock(self, event):
        if event.data.clock_event in ('open', 'continue', 'close'):
            self.sell_strategy()
            self.buy_strategy()
        self.check_orders()

    def log_handler(self):
        cpath_current = os.path.dirname(os.path.dirname(__file__))
        cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
        log_filepath = os.path.join(cpath, 'log', f'{self.name}.log')
        return DefaultLogHandler(self.name, log_type='file', filepath=log_filepath)

    def shutdown(self):
        self.log.info("关闭前保存策略数据")
