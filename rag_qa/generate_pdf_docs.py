# -*- coding:utf-8 -*-
"""
生成 PDF 版本的文档

使用方法:
    python generate_pdf_docs.py
    
依赖:
    pip install markdown2 pdfkit
    
注意:
    需要先安装 wkhtmltopdf:
    - Windows: https://wkhtmltopdf.org/downloads.html
    - Linux: sudo apt-get install wkhtmltopdf
"""
import os
import sys
from pathlib import Path

try:
    import markdown2
    import pdfkit
except ImportError as e:
    print("❌ 缺少依赖库")
    print("\n请安装:")
    print("  pip install markdown2 pdfkit")
    print("\n并安装 wkhtmltopdf:")
    print("  Windows: https://wkhtmltopdf.org/downloads.html")
    print("  Linux: sudo apt-get install wkhtmltopdf")
    sys.exit(1)


def convert_md_to_pdf(md_file, output_dir="./docs_pdf"):
    """
    将 Markdown 文件转换为 PDF
    
    Args:
        md_file: Markdown 文件路径
        output_dir: PDF 输出目录
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 读取 Markdown 文件
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # 转换为 HTML
    html_content = markdown2.markdown(
        md_content,
        extras=['tables', 'fenced-code-blocks', 'toc', 'header-ids']
    )
    
    # 添加 CSS 样式
    styled_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: "Microsoft YaHei", Arial, sans-serif;
                line-height: 1.6;
                margin: 40px;
                color: #333;
            }}
            h1, h2, h3, h4, h5, h6 {{
                color: #2c3e50;
                margin-top: 30px;
                margin-bottom: 20px;
            }}
            h1 {{ border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            h2 {{ border-bottom: 1px solid #bdc3c7; padding-bottom: 8px; }}
            code {{
                background-color: #f4f4f4;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: "Consolas", "Courier New", monospace;
            }}
            pre {{
                background-color: #282c34;
                color: #abb2bf;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
            }}
            pre code {{
                background-color: transparent;
                color: inherit;
                padding: 0;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 20px 0;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 10px;
                text-align: left;
            }}
            th {{
                background-color: #3498db;
                color: white;
            }}
            tr:nth-child(even) {{
                background-color: #f9f9f9;
            }}
            blockquote {{
                border-left: 4px solid #3498db;
                margin: 20px 0;
                padding-left: 20px;
                color: #666;
            }}
            a {{
                color: #3498db;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .page-break {{
                page-break-after: always;
            }}
        </style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """
    
    # 生成 PDF 文件名
    base_name = os.path.basename(md_file).replace('.md', '.pdf')
    output_path = os.path.join(output_dir, base_name)
    
    # 配置 PDF 选项
    options = {
        'page-size': 'A4',
        'margin-top': '20mm',
        'margin-right': '20mm',
        'margin-bottom': '20mm',
        'margin-left': '20mm',
        'encoding': 'UTF-8',
        'footer-center': '[page]',
        'footer-font-size': '10',
        'footer-spacing': '10'
    }
    
    try:
        # 转换为 PDF
        pdfkit.from_string(styled_html, output_path, options=options)
        print(f"✅ 成功生成：{output_path}")
        return True
    except Exception as e:
        print(f"❌ 转换失败：{e}")
        return False


def main():
    """主函数"""
    print("="*80)
    print("📄 EduRAG PDF 文档生成器")
    print("="*80)
    
    # 项目根目录
    project_root = Path(__file__).parent
    
    # 要转换的文档列表
    docs_to_convert = [
        project_root / "README.md",
        project_root / "项目使用指南.md",
        project_root / "会话管理使用指南.md",
    ]
    
    # 统计
    success_count = 0
    failed_count = 0
    
    print(f"\n准备转换 {len(docs_to_convert)} 个文档...\n")
    
    for doc_path in docs_to_convert:
        if not doc_path.exists():
            print(f"⚠️  文件不存在：{doc_path}")
            failed_count += 1
            continue
        
        print(f"正在处理：{doc_path.name}")
        
        if convert_md_to_pdf(str(doc_path)):
            success_count += 1
        else:
            failed_count += 1
    
    # 输出结果
    print("\n" + "="*80)
    print("📊 转换结果:")
    print(f"  ✅ 成功：{success_count} 个")
    print(f"  ❌ 失败：{failed_count} 个")
    print(f"  📁 输出目录：./docs_pdf/")
    print("="*80)
    
    if success_count > 0:
        print("\n💡 提示：PDF 文件已保存到 docs_pdf/ 目录")
        print("   可以使用 Adobe Reader 或其他 PDF 阅读器打开查看")


if __name__ == '__main__':
    main()
