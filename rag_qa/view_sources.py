# -*- coding:utf-8 -*-
"""
RAG 知识库溯源查看工具（增强版）
功能：溯源查看 + 统计分析 + 结果导出
"""
import sys
import os
import json
import csv
from datetime import datetime
from collections import Counter
from pathlib import Path
from typing import List, Optional, Dict

# 添加项目路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from core.vector_store import VectorStore
from base import Config, logger


class SourceViewer:
    """溯源查看器类"""
    
    def __init__(self):
        """初始化查看器"""
        self.vector_store = None
        self.last_results = []
        self.last_query = ""
        self.conf = Config()
        
    def _init_vector_store(self):
        """延迟初始化向量存储"""
        if self.vector_store is None:
            print("\n正在连接 Milvus 数据库...")
            try:
                self.vector_store = VectorStore()
                print("✅ Milvus 连接成功")
            except Exception as e:
                print(f"❌ Milvus 连接失败：{e}")
                logger.error(f"Milvus 连接失败：{e}")
                raise
    
    def view(self, query: str, top_k: int = 5, source_filter: str = None, 
             show_stats: bool = True, show_detail: bool = True) -> List:
        """
        查看检索结果并显示统计
        
        Args:
            query: 用户查询
            top_k: 显示前 K 个结果
            source_filter: 学科过滤（如 "mining", "ai"）
            show_stats: 是否显示统计信息
            show_detail: 是否显示详细内容
            
        Returns:
            检索结果列表
        """
        self.last_query = query
        
        # 初始化向量存储
        self._init_vector_store()
        
        # 执行检索
        print(f"\n正在执行混合检索 (top_k={top_k}, source_filter={source_filter})...")
        try:
            results = self.vector_store.hybrid_search_with_rerank(
                query=query, 
                k=top_k, 
                source_filter=source_filter
            )
            self.last_results = results
            print(f"✅ 检索到 {len(results)} 个相关文档\n")
        except Exception as e:
            print(f"❌ 检索失败：{e}")
            logger.error(f"检索失败：{e}")
            return []
        
        # 显示溯源信息
        if show_detail and results:
            self._display_sources(results, query)
        
        # 显示统计
        if show_stats and results:
            self._display_statistics(results)
        
        return results
    
    def _display_sources(self, results: List, query: str):
        """格式化显示溯源信息"""
        print("\n" + "="*80)
        print(f"🔍 查询：{query}")
        print("="*80)
        
        for i, doc in enumerate(results, 1):
            # 提取元数据
            metadata = doc.metadata
            
            # 构建来源信息卡片
            card = f"""
[文档 {i}] {'='*60}
├─ 📁 学科类别：{metadata.get('source', 'N/A')}
├─ 📄 文件名称：{os.path.basename(metadata.get('file_path', 'N/A'))}
├─ 📍 完整路径：{metadata.get('file_path', 'N/A')}
├─ 🔗 父块 ID:  {metadata.get('parent_id', 'N/A')}
├─ ⏰ 入库时间：{metadata.get('timestamp', 'N/A')}
└─ 📖 内容摘要:
   {doc.page_content[:200]}{'...' if len(doc.page_content) > 200 else ''}
"""
            print(card)
        
        print("="*80)
    
    def _display_statistics(self, results: List):
        """显示统计信息"""
        sources = [doc.metadata.get('source', 'unknown') for doc in results]
        files = [os.path.basename(doc.metadata.get('file_path', 'N/A')) for doc in results]
        
        # 去重统计
        unique_sources = set(sources)
        unique_files = set(files)
        
        print("\n📊 统计信息:")
        print(f"  检索文档总数：{len(results)}")
        print(f"  涉及学科数：{len(unique_sources)}")
        print(f"  涉及文件数：{len(unique_files)}")
        
        # 学科分布
        source_counts = Counter(sources)
        print("\n  学科分布:")
        max_count = max(source_counts.values()) if source_counts else 0
        bar_scale = 40 / max_count if max_count > 0 else 1
        
        for source, count in sorted(source_counts.items()):
            bar = "█" * int(count * bar_scale)
            percentage = (count / len(results)) * 100
            print(f"    {source:15} {bar:<40} ({count}, {percentage:.1f}%)")
        
        # 文件分布
        file_counts = Counter(files)
        print("\n  文件分布:")
        for file, count in sorted(file_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"    {file:30} ({count}次)")
    
    def export_to_json(self, filename: str = None, include_stats: bool = True) -> str:
        """
        导出结果为 JSON
        
        Args:
            filename: 输出文件名（默认自动生成）
            include_stats: 是否包含统计信息
            
        Returns:
            输出的文件路径
        """
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"sources_{timestamp}.json"
        
        export_data = {
            'query': self.last_query,
            'export_time': datetime.now().isoformat(),
            'total_results': len(self.last_results),
            'sources': []
        }
        
        # 导出每个文档的详细信息
        for i, doc in enumerate(self.last_results, 1):
            doc_data = {
                'index': i,
                'source': doc.metadata.get('source'),
                'file_path': doc.metadata.get('file_path'),
                'file_name': os.path.basename(doc.metadata.get('file_path', 'N/A')),
                'parent_id': doc.metadata.get('parent_id'),
                'timestamp': doc.metadata.get('timestamp'),
                'content': doc.page_content,
                'score': doc.metadata.get('score')
            }
            export_data['sources'].append(doc_data)
        
        # 添加统计信息
        if include_stats:
            sources = [doc.metadata.get('source', 'unknown') for doc in self.last_results]
            files = [os.path.basename(doc.metadata.get('file_path', 'N/A')) for doc in self.last_results]
            
            export_data['statistics'] = {
                'total_docs': len(self.last_results),
                'unique_sources': len(set(sources)),
                'unique_files': len(set(files)),
                'source_distribution': dict(Counter(sources)),
                'file_distribution': dict(Counter(files))
            }
        
        # 保存到文件
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ JSON 结果已导出至：{filename}")
        return filename
    
    def export_to_csv(self, filename: str = None) -> str:
        """
        导出结果为 CSV
        
        Args:
            filename: 输出文件名（默认自动生成）
            
        Returns:
            输出的文件路径
        """
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"sources_{timestamp}.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            
            # 写入表头
            writer.writerow([
                '序号', '学科', '文件名', '完整路径', '父块 ID', 
                '入库时间', '相关性得分', '内容摘要'
            ])
            
            # 写入数据
            for i, doc in enumerate(self.last_results, 1):
                writer.writerow([
                    i,
                    doc.metadata.get('source', 'N/A'),
                    os.path.basename(doc.metadata.get('file_path', 'N/A')),
                    doc.metadata.get('file_path', 'N/A'),
                    doc.metadata.get('parent_id', 'N/A'),
                    doc.metadata.get('timestamp', 'N/A'),
                    doc.metadata.get('score', 'N/A'),
                    doc.page_content[:200]  # 限制内容长度
                ])
        
        print(f"\n✅ CSV 结果已导出至：{filename}")
        return filename
    
    def export_to_markdown(self, filename: str = None) -> str:
        """
        导出结果为 Markdown 格式
        
        Args:
            filename: 输出文件名（默认自动生成）
            
        Returns:
            输出的文件路径
        """
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"sources_{timestamp}.md"
        
        with open(filename, 'w', encoding='utf-8') as f:
            # 标题
            f.write(f"# RAG 知识库溯源报告\n\n")
            f.write(f"**查询**: {self.last_query}  \n")
            f.write(f"**导出时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
            f.write(f"**检索结果数**: {len(self.last_results)}\n\n")
            
            # 统计信息
            f.write("## 📊 统计信息\n\n")
            sources = [doc.metadata.get('source', 'unknown') for doc in self.last_results]
            files = [os.path.basename(doc.metadata.get('file_path', 'N/A')) for doc in self.last_results]
            
            f.write(f"- 检索文档总数：{len(self.last_results)}\n")
            f.write(f"- 涉及学科数：{len(set(sources))}\n")
            f.write(f"- 涉及文件数：{len(set(files))}\n\n")
            
            # 学科分布
            f.write("### 学科分布\n\n")
            source_counts = Counter(sources)
            for source, count in sorted(source_counts.items()):
                percentage = (count / len(self.last_results)) * 100
                f.write(f"- **{source}**: {count} ({percentage:.1f}%)\n")
            f.write("\n")
            
            # 详细溯源
            f.write("## 📚 详细溯源\n\n")
            for i, doc in enumerate(self.last_results, 1):
                metadata = doc.metadata
                f.write(f"### [文档 {i}]\n\n")
                f.write(f"- **学科**: {metadata.get('source', 'N/A')}\n")
                f.write(f"- **文件名**: `{os.path.basename(metadata.get('file_path', 'N/A'))}`\n")
                f.write(f"- **路径**: {metadata.get('file_path', 'N/A')}\n")
                f.write(f"- **父块 ID**: {metadata.get('parent_id', 'N/A')}\n")
                f.write(f"- **入库时间**: {metadata.get('timestamp', 'N/A')}\n")
                f.write(f"- **相关性得分**: {metadata.get('score', 'N/A')}\n")
                f.write(f"\n**内容摘要**:\n> {doc.page_content[:300]}{'...' if len(doc.page_content) > 300 else ''}\n")
                f.write("\n---\n\n")
        
        print(f"\n✅ Markdown 结果已导出至：{filename}")
        return filename


def interactive_mode():
    """交互模式"""
    viewer = SourceViewer()
    
    print("\n" + "="*80)
    print("🔍 RAG 知识库溯源查看工具 - 交互模式")
    print("="*80)
    print("\n💡 使用提示:")
    print("  - 直接输入问题即可查看溯源信息")
    print("  - 输入 'export json' 导出最近一次结果为 JSON")
    print("  - 输入 'export csv' 导出最近一次结果为 CSV")
    print("  - 输入 'export md' 导出最近一次结果为 Markdown")
    print("  - 输入 'stats' 重新显示统计信息")
    print("  - 输入 'exit' 或 'quit' 退出")
    print("="*80 + "\n")
    
    while True:
        try:
            user_input = input("🔍 请输入查询：").strip()
            
            if not user_input:
                continue
            
            # 处理命令
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("\n再见！")
                break
            
            elif user_input.lower() == 'stats':
                if viewer.last_results:
                    viewer._display_statistics(viewer.last_results)
                else:
                    print("⚠️  请先执行一次查询")
                continue
            
            elif user_input.lower().startswith('export'):
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
                    print("❌ 不支持的格式，请使用：json, csv, md")
                continue
            
            # 执行查询
            viewer.view(
                query=user_input,
                top_k=5,
                show_stats=True,
                show_detail=True
            )
            
        except KeyboardInterrupt:
            print("\n\n程序中断，再见！")
            break
        except Exception as e:
            print(f"\n❌ 发生错误：{e}")
            logger.error(f"交互模式出错：{e}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="RAG 知识库溯源查看工具（增强版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s -q "露天矿山开采工艺流程是什么？"
  %(prog)s -q "充填采矿法" -k 10 -s mining
  %(prog)s --interactive
  %(prog)s -q "AI 是什么" --export json
        """
    )
    
    parser.add_argument('-q', '--query', type=str, help='要查询的问题')
    parser.add_argument('-k', '--top-k', type=int, default=5, help='显示前 K 个结果 (默认:5)')
    parser.add_argument('-s', '--source', type=str, help='学科过滤 (如:mining,ai,java)')
    parser.add_argument('-i', '--interactive', action='store_true', help='交互模式')
    parser.add_argument('--export', type=str, choices=['json', 'csv', 'md'], help='导出格式')
    parser.add_argument('--output', '-o', type=str, help='输出文件名')
    parser.add_argument('--no-stats', action='store_true', help='不显示统计信息')
    parser.add_argument('--no-detail', action='store_true', help='不显示详细内容')
    
    args = parser.parse_args()
    
    # 交互模式
    if args.interactive or not args.query:
        interactive_mode()
        return
    
    # 命令行模式
    viewer = SourceViewer()
    
    try:
        # 执行查询
        viewer.view(
            query=args.query,
            top_k=args.top_k,
            source_filter=args.source,
            show_stats=not args.no_stats,
            show_detail=not args.no_detail
        )
        
        # 导出结果
        if args.export:
            if args.export == 'json':
                viewer.export_to_json(args.output)
            elif args.export == 'csv':
                viewer.export_to_csv(args.output)
            elif args.export == 'md':
                viewer.export_to_markdown(args.output)
    
    except Exception as e:
        print(f"\n❌ 执行失败：{e}")
        logger.error(f"命令行模式出错：{e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
