"""Embedding生成入口脚本：构建search_text + 生成embedding向量"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import init_db
from src.embedding import batch_build_search_text, batch_generate_embeddings


def main():
    if not os.environ.get('OPENAI_API_KEY'):
        print("错误: 请设置 OPENAI_API_KEY 环境变量")
        sys.exit(1)

    init_db()

    # Step 1: 构建search_text
    print("=== Step 1: 构建search_text ===")
    st_count = batch_build_search_text()

    # Step 2: 生成embedding
    print()
    print("=== Step 2: 生成embedding ===")
    emb_count = batch_generate_embeddings()

    print()
    print(f"总结: search_text {st_count} 个, embedding {emb_count} 个")


if __name__ == "__main__":
    main()
