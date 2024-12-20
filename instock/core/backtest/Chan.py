import os
import random
import sys
from datetime import datetime, timedelta

import backtrader as bt
import pandas as pd
import matplotlib

from instock.core.backtest.base_strategy import BaseStrategy
from instock.core.singleton_stock import stock_hist_data, stock_data
from instock.lib.singleton_type import singleton_type
import instock.core.tablestructure as tbs

cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
sys.path.append(cpath)

class ChanKline:
    def __init__(self, open, high, low, close, date, volume):
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.date = date
        self.volume = volume

class Segment:
    def __init__(self, start, end, direction):
        self.start = start
        self.end = end
        self.direction = direction  # 1 for up, -1 for down

class Pivot:
    def __init__(self, kline, type):
        self.kline = kline
        self.type = type  # 'high' or 'low'

class CentralZone:
    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.high = max(start.high, end.high)
        self.low = min(start.low, end.low)

class ChanIndicator(bt.Indicator):
    lines = ('buy_signal', 'sell_signal')
    params = (
        ('period', 20),
        ('atr_period', 14),
        ('atr_multiplier', 2),
    )

    def __init__(self):
        self.addminperiod(self.params.period)
        self.merged_klines = []
        self.segments = []
        self.pivots = []
        self.central_zones = []
        
        # 添加技术指标
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_period)
        self.rsi = bt.indicators.RSI(self.data, period=14)
        self.macd = bt.indicators.MACD(self.data)
        self.volume_ma = bt.indicators.SMA(self.data.volume, period=20)

    def next(self):
        current_kline = ChanKline(self.data.open[0], self.data.high[0], self.data.low[0], 
                                  self.data.close[0], self.data.datetime.date(0), self.data.volume[0])
        self.merge_klines(current_kline)
        self.identify_pivots()
        self.identify_segments()
        self.identify_central_zones()

        self.lines.buy_signal[0] = self.is_buy_point()
        self.lines.sell_signal[0] = self.is_sell_point()

    def merge_klines(self, new_kline):
        # 保持原有的K线合并逻辑
        if not self.merged_klines:
            self.merged_klines.append(new_kline)
            return

        last_kline = self.merged_klines[-1]
        if (new_kline.high > last_kline.high and new_kline.low < last_kline.low) or \
           (new_kline.high < last_kline.high and new_kline.low > last_kline.low):
            merged_kline = ChanKline(
                last_kline.open,
                max(last_kline.high, new_kline.high),
                min(last_kline.low, new_kline.low),
                new_kline.close,
                new_kline.date,
                last_kline.volume + new_kline.volume
            )
            self.merged_klines[-1] = merged_kline
        else:
            self.merged_klines.append(new_kline)

    def identify_pivots(self):
        # 保持原有的顶底点识别逻辑
        if len(self.merged_klines) < 3:
            return

        for i in range(1, len(self.merged_klines) - 1):
            prev, curr, next = self.merged_klines[i-1:i+2]
            if curr.high > prev.high and curr.high > next.high:
                self.pivots.append(Pivot(curr, 'high'))
            elif curr.low < prev.low and curr.low < next.low:
                self.pivots.append(Pivot(curr, 'low'))

    def identify_segments(self):
        # 保持原有的线段识别逻辑
        if len(self.pivots) < 2:
            return

        for i in range(len(self.pivots) - 1):
            start, end = self.pivots[i], self.pivots[i+1]
            if start.type != end.type:
                direction = 1 if start.type == 'low' else -1
                self.segments.append(Segment(start.kline, end.kline, direction))

    def identify_central_zones(self):
        # 优化中枢识别逻辑
        if len(self.segments) < 3:
            return

        for i in range(len(self.segments) - 2):
            seg1, seg2, seg3 = self.segments[i:i+3]
            if seg1.direction != seg3.direction:
                overlap_high = min(seg1.end.high, seg2.end.high, seg3.start.high)
                overlap_low = max(seg1.end.low, seg2.end.low, seg3.start.low)
                if overlap_high > overlap_low:
                    zone = CentralZone(seg1.end, seg3.start)
                    if not self.central_zones or zone.low > self.central_zones[-1].high or zone.high < self.central_zones[-1].low:
                        self.central_zones.append(zone)

    def is_buy_point(self):
        if not self.central_zones:
            return 0

        last_zone = self.central_zones[-1]
        last_kline = self.merged_klines[-1]
        prev_kline = self.merged_klines[-2]

        # 趋势判断
        trend = self.judge_trend()

        # 第一类买点：突破中枢上沿
        if prev_kline.close <= last_zone.high and last_kline.close > last_zone.high and trend == 1:
            return 1

        # 第二类买点：回调不破中枢
        if self.lines.buy_signal[-1] == 1 and last_kline.low > last_zone.low and trend == 1:
            return 2

        # 第三类买点：中枢震荡突破
        if last_zone.low < last_kline.close < last_zone.high and self.is_volume_breakout() and trend == 1:
            return 3

        return 0

    def is_sell_point(self):
        if not self.central_zones:
            return 0

        last_zone = self.central_zones[-1]
        last_kline = self.merged_klines[-1]

        # 趋势判断
        trend = self.judge_trend()

        # 第一类卖点：跌破中枢下沿
        if last_kline.close < last_zone.low and self.merged_klines[-2].close >= last_zone.low and trend == -1:
            return 1

        # 第二类卖点：反弹不破中枢
        if self.lines.sell_signal[-1] == 1 and last_kline.high < last_zone.high and trend == -1:
            return 2

        # 第三类卖点：中枢震荡突破下沿
        if last_zone.low < last_kline.close < last_zone.high and self.is_volume_breakout() and trend == -1:
            return 3

        return 0

    def judge_trend(self):
        # 使用MACD判断趋势
        if self.macd.macd[0] > self.macd.signal[0] and self.macd.macd[0] > 0:
            return 1  # 上升趋势
        elif self.macd.macd[0] < self.macd.signal[0] and self.macd.macd[0] < 0:
            return -1  # 下降趋势
        else:
            return 0  # 震荡

    def is_volume_breakout(self):
        # 判断是否出现放量
        return self.data.volume[0] > self.volume_ma[0] * 1.5

    def is_divergence(self, seg1, seg2):
        # 判断背驰
        price_change1 = abs(seg1.end.close - seg1.start.close)
        price_change2 = abs(seg2.end.close - seg2.start.close)
        volume1 = sum([k.volume for k in self.merged_klines[self.merged_klines.index(seg1.start):self.merged_klines.index(seg1.end)+1]])
        volume2 = sum([k.volume for k in self.merged_klines[self.merged_klines.index(seg2.start):self.merged_klines.index(seg2.end)+1]])
        return (seg1.direction == seg2.direction) and (price_change2 > price_change1) and (volume2 < volume1)

class ImprovedChanStrategy(BaseStrategy):
    params = (
        ('atr_period', 14),
        ('atr_multiplier', 2),
    )

    def __init__(self):
        super().__init__()
        self.chan_indicators = {}
        for d in self.datas:
            self.chan_indicators[d] = ChanIndicator(d, period=20, atr_period=self.params.atr_period, atr_multiplier=self.params.atr_multiplier)

    def next(self):
        for data in self.datas:
            self.process_data(data)

    def process_data(self, data):
        if self.orders.get(data):
            return

        position = self.getposition(data)
        buy_signal = self.chan_indicators[data].buy_signal[0]
        sell_signal = self.chan_indicators[data].sell_signal[0]

        if not position:
            if buy_signal > 0:
                self.log(f'创建买入订单: {data._name} (买点类型: {buy_signal}), 价格: {data.close[0]}')
                self.buy_stock(data)
        else:
            if sell_signal > 0:
                self.log(f'创建卖出订单: {data._name} (卖点类型: {sell_signal}), 价格: {data.close[0]}')
                self.close(data)

        self.check_stop_loss(data)

    def check_stop_loss(self, data):
        position = self.getposition(data)
        if not position:
            return

        atr = self.chan_indicators[data].atr[0]
        current_stop = self.buyprice[data] - self.params.atr_multiplier * atr

        if data.close[0] < current_stop:
            self.log(f'触发动态止损: {data._name}, 价格: {data.close[0]}')
            self.close(data)

    def buy_stock(self, data, size=None):
        if size is None:
            size = self.calculate_buy_size(data)
        if size > 0:
            self.orders[data] = self.buy(data=data, size=size)
            self.position_value[data] = size * data.close[0]
            self.buyprice[data] = data.close[0]
        else:
            self.log(f'可用资金不足，无法买入: {data._name}, 可用资金: {self.broker.getvalue() - sum(self.position_value.values())}')

    def calculate_buy_size(self, data):
        available_cash = self.broker.getvalue() - sum(self.position_value.values())
        if available_cash <= 0:
            return 0
        risk_per_trade = self.broker.getvalue() * 0.01  # 风险控制：每次交易最多损失账户1%的资金
        atr = self.chan_indicators[data].atr[0]
        stop_loss = data.close[0] - self.params.atr_multiplier * atr
        shares = int(risk_per_trade / (data.close[0] - stop_loss))
        return min(shares, int(available_cash / data.close[0]))


