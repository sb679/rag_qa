"""
敏感信息扫描工具
在上传到 GitHub 前运行此脚本，确保没有遗漏敏感信息
"""
import os
import re
from pathlib import Path

def scan_for_sensitive_info(root_dir='.'):
    """扫描项目中的敏感信息"""
    
    # 定义敏感模式
    sensitive_patterns = {
        'API Key (DashScope/DeepSeek)': r'sk-[a-zA-Z0-9]{20,}',
        '电话号码': r'1[3-9]\d{9}',  # 中国大陆手机号格式
        'MySQL 密码': r'password\s*=\s*123456',
        'Redis 密码': r'password\s*=\s*1234[^_]',
    }
    
    # 要扫描的文件扩展名
    file_extensions = ['.py', '.md', '.ini', '.txt', '.json', '.yaml', '.yml']
    
    # 要排除的目录
    exclude_dirs = {
        '.git', '__pycache__', 'node_modules', 
        'models', 'bert_results', 'bert_strategy_results',
        '.idea', '.vscode'
    }
    
    # 要排除的文件（包含误报数据）
    exclude_files = {
        '.ocr_cache.json',  # OCR 缓存包含数字序列
        'tokenizer_config.json',  # tokenizer 配置包含超大数值
    }
    
    findings = []
    
    print("=" * 70)
    print("敏感信息扫描工具")
    print("=" * 70)
    print()
    
    for root, dirs, files in os.walk(root_dir):
        # 排除指定目录
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            file_path = os.path.join(root, file)
            ext = os.path.splitext(file)[1]
            
            # 排除特定文件
            if any(file.endswith(excl) for excl in exclude_files):
                continue
            
            if ext not in file_extensions:
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                    for pattern_name, pattern in sensitive_patterns.items():
                        matches = re.finditer(pattern, content, re.IGNORECASE)
                        
                        for match in matches:
                            # 获取匹配行的上下文
                            start = max(0, match.start() - 50)
                            end = min(len(content), match.end() + 50)
                            context = content[start:end].replace('\n', ' ')
                            
                            # 跳过占位符
                            if 'YOUR_' in match.group() or 'your-' in match.group().lower():
                                continue
                            
                            findings.append({
                                'file': file_path,
                                'pattern': pattern_name,
                                'match': match.group(),
                                'context': context
                            })
            except Exception as e:
                pass
    
    # 输出结果
    if findings:
        print(f"⚠️  发现 {len(findings)} 个潜在的敏感信息:\n")
        
        for i, finding in enumerate(findings, 1):
            print(f"{i}. 文件: {finding['file']}")
            print(f"   类型: {finding['pattern']}")
            print(f"   匹配: {finding['match']}")
            print(f"   上下文: ...{finding['context']}...")
            print()
        
        print("=" * 70)
        print("❌ 建议在上传前清理以上敏感信息")
        print("=" * 70)
        return False
    else:
        print("✅ 未发现敏感信息！")
        print()
        print("已扫描的模式:")
        for pattern_name in sensitive_patterns.keys():
            print(f"  ✓ {pattern_name}")
        print()
        print("=" * 70)
        print("✅ 可以安全上传到 GitHub")
        print("=" * 70)
        return True

def check_gitignore():
    """检查 .gitignore 配置"""
    print("\n" + "=" * 70)
    print("检查 .gitignore 配置")
    print("=" * 70)
    print()
    
    gitignore_path = '.gitignore'
    if not os.path.exists(gitignore_path):
        print("❌ 未找到 .gitignore 文件")
        return False
    
    with open(gitignore_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    required_patterns = [
        ('config.ini', '配置文件'),
        ('pytorch_model.bin', '模型权重文件'),
        ('__pycache__', 'Python 缓存'),
        ('.idea/', 'IDE 配置'),
        ('*.log', '日志文件'),
    ]
    
    all_good = True
    for pattern, description in required_patterns:
        if pattern in content:
            print(f"✅ {description}: {pattern}")
        else:
            print(f"❌ {description}: {pattern} (缺失)")
            all_good = False
    
    print()
    if all_good:
        print("✅ .gitignore 配置完整")
    else:
        print("⚠️  .gitignore 缺少部分重要规则")
    
    return all_good

if __name__ == "__main__":
    print("开始扫描项目...\n")
    
    # 扫描敏感信息
    scan_result = scan_for_sensitive_info('.')
    
    # 检查 .gitignore
    gitignore_result = check_gitignore()
    
    print("\n" + "=" * 70)
    print("总结")
    print("=" * 70)
    
    if scan_result and gitignore_result:
        print("✅ 所有检查通过，可以安全上传到 GitHub！")
    else:
        print("⚠️  存在需要处理的问题，请查看上述报告")
    
    print("=" * 70)
