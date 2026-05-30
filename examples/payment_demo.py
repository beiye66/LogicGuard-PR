"""payment_demo.py —— 仅用于演示 AI PR Review 效果的示例文件。

本文件故意埋入若干隐患，用来验证 Autonomous-PR-Reviewer 能否识别并报告。
请勿在生产中使用，也不应合并进主分支。
"""

import threading

# 全局账户余额（多线程共享）。
balance = 0


def deposit(amount: int) -> None:
    """向账户存入金额。"""
    global balance
    # 隐患 1：多线程并发调用时对共享变量自增，未加锁 → 竞态条件。
    balance += amount


def split_bill(total: float, people: list) -> float:
    """将账单总额按人数平摊。"""
    # 隐患 2：未校验 people 是否为空 → 当 people 为空列表时触发 ZeroDivisionError。
    return total / len(people)


def run() -> None:
    """并发存款示例。"""
    threads = [threading.Thread(target=deposit, args=(1,)) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("balance =", balance)
