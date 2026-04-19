# -*- coding:utf-8 -*-
"""
场景 3: 知识库溯源 - 查看检索结果的来源

使用方法:
    python examples_03_view_sources.py
"""
import sys, os
from pathlib import Path

# 添加项目路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from view_sources import SourceViewer


def demo_basic_usage():
    """基础用法演示"""
    print("="*80)
    print("🔍 知识库溯源查看 - 基础演示")
    print("="*80)
    
    viewer = SourceViewer()
    
    # 示例查询
    test_queries = [
        "露天矿山开采工艺流程",
        "充填采矿法的适用条件",
        "深部开采地压控制技术"
    ]
    
    for query in test_queries:
        print(f"\n{'='*80}")
        print(f"查询：{query}")
        print(f"{'='*80}")
        
        results = viewer.view(
            query=query,
            top_k=3,
            show_stats=True
        )
        
        if results:
            print(f"\n✅ 检索到 {len(results)} 个相关文档")
        else:
            print("\n⚠️  未找到相关文档")
        
        input("\n按回车键继续下一个查询...")


def demo_export_features():
    """导出功能演示"""
    print("\n" + "="*80)
    print("📤 溯源导出功能演示")
    print("="*80)
    
    viewer = SourceViewer()
    
    # 执行查询
    query = "露天开采工艺"
    print(f"\n执行查询：{query}")
    
    viewer.view(query=query, top_k=5, show_stats=False)
    
    if not viewer.last_results:
        print("⚠️  没有检索结果，无法演示导出功能")
        return
    
    # 导出为 JSON
    print("\n正在导出为 JSON...")
    json_file = viewer.export_to_json("demo_sources.json")
    
    # 导出为 CSV
    print("\n正在导出为 CSV...")
    csv_file = viewer.export_to_csv("demo_sources.csv")
    
    # 导出为 Markdown
    print("\n正在导出为 Markdown...")
    md_file = viewer.export_to_markdown("demo_sources.md")
    
    print("\n✅ 导出完成！生成的文件:")
    print(f"  - {json_file}")
    print(f"  - {csv_file}")
    print(f"  - {md_file}")


def interactive_mode():
    """交互模式"""
    print("\n" + "="*80)
    print("🔍 知识库溯源查看器 - 交互模式")
    print("="*80)
    print("\n💡 使用说明:")
    print("  - 直接输入问题查看溯源")
    print("  - 输入 'export json' 导出 JSON")
    print("  - 输入 'export csv' 导出 CSV")
    print("  - 输入 'export md' 导出 Markdown")
    print("  - 输入 'stats' 显示统计")
    print("  - 输入 'exit' 退出")
    print("="*80 + "\n")
    
    viewer = SourceViewer()
    
    while True:
        try:
            user_input = input("🔍 请输入查询：").strip()
            
            if not user_input:
                continue
            
            # 处理命令
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("\n再见！")
                break
            
            if user_input.lower() == 'stats':
                if viewer.last_results:
                    viewer._display_statistics(viewer.last_results)
                else:
                    print("⚠️  请先执行一次查询")
                continue
            
            if user_input.lower().startswith('export'):
                parts = user_input.split()
                if len(parts) < 2:
                    print("❌ 用法：export [json|csv|md]")
                    continue
                
                format_type = parts[1].lower()
                if format_type == 'json':
                    viewer.export_to_json()
                elif format_type == 'csv':
                    viewer.export_to_csv()
                elif format_type == 'md':
                    viewer.export_to_markdown()
                else:
                    print("❌ 不支持的格式")
                continue
            
            # 执行查询
            viewer.view(
                query=user_input,
                top_k=5,
                show_stats=True
            )
            
        except KeyboardInterrupt:
            print("\n\n程序中断")
            break
        except Exception as e:
            print(f"\n❌ 发生错误：{e}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description="知识库溯源查看示例")
    parser.add_argument('--demo', action='store_true', help='运行基础演示')
    parser.add_argument('--export-demo', action='store_true', help='运行导出演示')
    parser.add_argument('-i', '--interactive', action='store_true', help='交互模式')
    
    args = parser.parse_args()
    
    if args.demo:
        demo_basic_usage()
    elif args.export_demo:
        demo_export_features()
    elif args.interactive:
        interactive_mode()
    else:
        # 默认运行交互模式
        interactive_mode()
