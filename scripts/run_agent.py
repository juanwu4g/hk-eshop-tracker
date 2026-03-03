#!/usr/bin/env python3
"""HK eShop 折扣助手 - AI Agent 命令行交互"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def main():
    parser = argparse.ArgumentParser(description='HK eShop 折扣助手')
    parser.add_argument('--debug', action='store_true',
                        help='开启 LangChain 全局 debug（打印完整 LLM 请求/响应）')
    args = parser.parse_args()

    # 检查 API key
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("错误：请设置 ANTHROPIC_API_KEY 环境变量")
        print("  export ANTHROPIC_API_KEY='your-api-key'")
        sys.exit(1)

    from src.database import init_db
    from src.agent.agent import create_agent, ask

    init_db()
    agent = create_agent(debug=args.debug)

    print("HK eShop 折扣助手（输入 quit 退出）")
    print("=" * 40)

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ('quit', 'exit', 'q'):
            print("再见！")
            break

        try:
            response = ask(agent, user_input)
            print(f"\n{response}")
        except Exception as e:
            print(f"\n出错了: {e}")


if __name__ == '__main__':
    main()
