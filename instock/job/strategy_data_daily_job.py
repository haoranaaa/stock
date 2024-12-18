#!/usr/local/bin/python3
# -*- coding: utf-8 -*-
import datetime
import logging
import concurrent.futures
import traceback

import pandas as pd
import os.path
import sys

cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
sys.path.append(cpath)
import instock.lib.run_template as runt
import instock.core.tablestructure as tbs
import instock.lib.database as mdb
from instock.core.singleton_stock import stock_hist_data
from instock.core.stockfetch import fetch_stock_top_entity_data

__author__ = 'myh '
__date__ = '2023/3/10 '


def prepare(date, strategy):
    try:
        stocks_data = stock_hist_data(date=date).get_data()
        if stocks_data is None:
            return
        table_name = strategy['name']
        strategy_func = strategy['func']
        results = run_check(strategy_func, table_name, stocks_data, date)
        if results is None:
            return

        # 删除老数据。
        if mdb.checkTableIsExist(table_name):
            del_sql = f"DELETE FROM `{table_name}` where `date` = '{date}'"
            mdb.executeSql(del_sql)
            cols_type = None
        else:
            cols_type = tbs.get_field_types(tbs.TABLE_CN_STOCK_STRATEGIES[0]['columns'])

        data = pd.DataFrame(results)
        columns = tuple(tbs.TABLE_CN_STOCK_FOREIGN_KEY['columns'])
        data.columns = columns
        _columns_backtest = tuple(tbs.TABLE_CN_STOCK_BACKTEST_DATA['columns'])
        data = pd.concat([data, pd.DataFrame(columns=_columns_backtest)])
        # 单例，时间段循环必须改时间
        date_str = date.strftime("%Y-%m-%d")
        if date.strftime("%Y-%m-%d") != data.iloc[0]['date']:
            data['date'] = date_str
        mdb.insert_db_from_df(data, table_name, cols_type, False, "`date`,`code`")
        # 增加买入数据


        # 取出stocks_data中key为results中值的数据
        buy_data = {k:stocks_data[k] for k in results}
        df_list = []  # 用于存储 DataFrame 行
        # 遍历 new_data，检查日期匹配
        # 遍历 buy_data，检查日期匹配
        for key, value in buy_data.items():
            date_key, code, name = key  # 解包键
            # 遍历值中的日期
            for i, date_value in enumerate(value['date']):
                if date_value == date_key:  # 如果日期匹配
                    # 使用字典解包简化行数据的创建
                    row = {
                        'date': date_value,
                        'code': code,
                        'name': name,
                        **{k: value[k][i] for k in
                           ['open', 'close', 'low', 'volume', 'amount', 'amplitude', 'high', 'quote_change',
                            'ups_downs', 'turnover', 'p_change']},
                    }
                    df_list.append(row)  # 添加到列表中
        df = pd.DataFrame(df_list)

        # 确保数据不为空

        # 删除老数据。
        buy_data_name_ = tbs.TABLE_CN_STOCK_BUY_DATA['name']
        if mdb.checkTableIsExist(buy_data_name_):
            del_sql = f"DELETE FROM `{buy_data_name_}` where `date` = '{date_str}'"
            mdb.executeSql(del_sql)
            cols_type = None
        else:
            cols_type = tbs.get_field_types(tbs.TABLE_CN_STOCK_BUY_DATA['columns'])

        # 插入新数据
        mdb.insert_db_from_df(df, buy_data_name_, cols_type, False, "`date`,`code`")
    except Exception as e:
        logging.error(f"strategy_data_daily_job.prepare处理异常：{strategy}策略{traceback.format_exc()}")


def run_check(strategy_fun, table_name, stocks, date, workers=40):
    is_check_high_tight = False
    if strategy_fun.__name__ == 'check_high_tight':
        stock_tops = fetch_stock_top_entity_data(date)
        if stock_tops is not None:
            is_check_high_tight = True
    data = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            if is_check_high_tight:
                future_to_data = {executor.submit(strategy_fun, k, stocks[k], date=date, istop=(k[1] in stock_tops)): k for k in stocks}
            else:
                future_to_data = {executor.submit(strategy_fun, k, stocks[k], date=date): k for k in stocks}
            for future in concurrent.futures.as_completed(future_to_data):
                stock = future_to_data[future]
                try:
                    if future.result():
                        data.append(stock)
                except Exception as e:
                    logging.error(f"strategy_data_daily_job.run_check处理异常：{stock[1]}代码{e}策略{table_name}")
    except Exception as e:
        logging.error(f"strategy_data_daily_job.run_check处理异常：{e}策略{table_name}")
    if not data:
        return None
    else:
        return data


def main():
    # 使用方法传递。
    with concurrent.futures.ThreadPoolExecutor() as executor:
        for strategy in tbs.TABLE_CN_STOCK_STRATEGIES:
            executor.submit(runt.run_with_args, prepare, strategy)


# main函数入口
if __name__ == '__main__':
    main()
