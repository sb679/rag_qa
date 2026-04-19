# -*- coding:utf-8 -*-
"""
OCR 进度检查和加速工具
用于监控 OCR 处理进度、清理缓存、重新处理等
"""

import os
import json
import sys
from pathlib import Path

# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from base import logger

def check_ocr_cache(data_dir="data"):
    """检查 OCR 缓存状态"""
    logger.info(f"检查目录：{data_dir}")
    
    total_files = 0
    cached_files = 0
    total_size = 0
    
    for root, dirs, files in os.walk(data_dir):
        for file in files:
            if file.endswith(('.pdf', '.docx', '.ppt', '.pptx')):
                total_files += 1
                file_path = os.path.join(root, file)
                cache_file_path = file_path + '.ocr_cache.json'
                
                # 获取文件大小
                try:
                    file_size = os.path.getsize(file_path)
                    total_size += file_size
                    
                    # 检查是否有缓存
                    if os.path.exists(cache_file_path):
                        cached_files += 1
                        logger.info(f"✓ 已缓存：{file}")
                        logger.info(f"  缓存文件：{cache_file_path}")
                        
                        # 验证缓存是否有效
                        try:
                            with open(cache_file_path, 'r', encoding='utf-8') as f:
                                cache_data = json.load(f)
                            
                            file_stat = os.stat(file_path)
                            if (cache_data.get('file_size') == file_stat.st_size and 
                                cache_data.get('file_mtime') == file_stat.st_mtime):
                                logger.info(f"  缓存状态：✓ 有效")
                            else:
                                logger.info(f"  缓存状态：⚠ 文件已修改，需要重新 OCR")
                        except Exception as e:
                            logger.info(f"  缓存状态：✗ 缓存损坏 ({e})")
                    else:
                        logger.info(f"✗ 未缓存：{file}")
                        logger.info(f"  需要进行 OCR 处理")
                except Exception as e:
                    logger.error(f"处理文件 {file} 时出错：{e}")
    
    # 打印统计信息
    print("\n" + "="*60)
    logger.info("OCR 缓存统计:")
    logger.info(f"  总文件数：{total_files}")
    logger.info(f"  已缓存数：{cached_files}")
    logger.info(f"  未缓存数：{total_files - cached_files}")
    logger.info(f"  缓存率：{cached_files/total_files*100:.2f}%" if total_files > 0 else "  无文件")
    logger.info(f"  总文件大小：{total_size / (1024*1024):.2f} MB")
    print("="*60)
    
    return {
        'total': total_files,
        'cached': cached_files,
        'uncached': total_files - cached_files,
        'total_size': total_size
    }

def clean_ocr_cache(data_dir="data", clean_all=False):
    """清理 OCR 缓存文件
    
    Args:
        data_dir: 数据目录
        clean_all: 是否清理所有缓存（False=只清理损坏的缓存）
    """
    logger.info(f"清理 OCR 缓存：{data_dir}")
    
    cleaned_count = 0
    cleaned_size = 0
    
    for root, dirs, files in os.walk(data_dir):
        for file in files:
            if file.endswith('.ocr_cache.json'):
                cache_file_path = os.path.join(root, file)
                
                if clean_all:
                    # 清理所有缓存
                    try:
                        cache_size = os.path.getsize(cache_file_path)
                        os.remove(cache_file_path)
                        cleaned_count += 1
                        cleaned_size += cache_size
                        logger.info(f"已删除：{cache_file_path}")
                    except Exception as e:
                        logger.error(f"删除缓存失败 {cache_file_path}: {e}")
                else:
                    # 只清理损坏或无效的缓存
                    try:
                        # 尝试从缓存文件名推断原文件路径
                        original_file = cache_file_path.replace('.ocr_cache.json', '')
                        if os.path.exists(original_file):
                            with open(cache_file_path, 'r', encoding='utf-8') as f:
                                cache_data = json.load(f)
                            
                            file_stat = os.stat(original_file)
                            if (cache_data.get('file_size') != file_stat.st_size or 
                                cache_data.get('file_mtime') != file_stat.st_mtime):
                                # 缓存无效，删除
                                cache_size = os.path.getsize(cache_file_path)
                                os.remove(cache_file_path)
                                cleaned_count += 1
                                cleaned_size += cache_size
                                logger.info(f"已删除无效缓存：{cache_file_path}")
                        else:
                            # 原文件不存在，删除缓存
                            cache_size = os.path.getsize(cache_file_path)
                            os.remove(cache_file_path)
                            cleaned_count += 1
                            cleaned_size += cache_size
                            logger.info(f"已删除孤儿缓存：{cache_file_path}")
                    except Exception as e:
                        # 缓存损坏，删除
                        try:
                            cache_size = os.path.getsize(cache_file_path)
                            os.remove(cache_file_path)
                            cleaned_count += 1
                            cleaned_size += cache_size
                            logger.info(f"已删除损坏缓存：{cache_file_path}")
                        except Exception as e2:
                            logger.error(f"删除缓存失败 {cache_file_path}: {e2}")
    
    logger.info(f"\n清理完成:")
    logger.info(f"  删除缓存文件数：{cleaned_count}")
    logger.info(f"  释放空间：{cleaned_size / (1024*1024):.2f} MB")

def estimate_processing_time(data_dir="data", pages_per_second=0.058):
    """估算剩余处理时间
    
    Args:
        data_dir: 数据目录
        pages_per_second: 每秒处理页数（根据实际测试，约 0.058 页/秒 = 17.31 秒/页）
    """
    import fitz  # PyMuPDF
    
    total_pages = 0
    cached_pages = 0
    
    for root, dirs, files in os.walk(data_dir):
        for file in files:
            if file.endswith('.pdf'):
                file_path = os.path.join(root, file)
                cache_file_path = file_path + '.ocr_cache.json'
                
                try:
                    # 获取 PDF 页数
                    doc = fitz.open(file_path)
                    pages = len(doc)
                    doc.close()
                    total_pages += pages
                    
                    # 检查是否有有效缓存
                    if os.path.exists(cache_file_path):
                        try:
                            with open(cache_file_path, 'r', encoding='utf-8') as f:
                                cache_data = json.load(f)
                            file_stat = os.stat(file_path)
                            if (cache_data.get('file_size') == file_stat.st_size and 
                                cache_data.get('file_mtime') == file_stat.st_mtime):
                                cached_pages += pages
                        except:
                            pass
                except Exception as e:
                    logger.error(f"统计 PDF 页数失败 {file}: {e}")
    
    uncached_pages = total_pages - cached_pages
    
    # 计算预计时间
    estimated_seconds = uncached_pages / pages_per_second if pages_per_second > 0 else 0
    estimated_hours = estimated_seconds / 3600
    
    print("\n" + "="*60)
    logger.info("处理时间估算:")
    logger.info(f"  总页数：{total_pages}")
    logger.info(f"  已处理页数：{cached_pages}")
    logger.info(f"  剩余页数：{uncached_pages}")
    logger.info(f"  处理速度：{pages_per_second:.4f} 页/秒")
    logger.info(f"  预计剩余时间：{estimated_hours:.2f} 小时 ({estimated_seconds:.0f} 秒)")
    logger.info(f"  按当前速度，完成日期：需要 {estimated_hours:.1f} 小时")
    print("="*60)
    
    return {
        'total_pages': total_pages,
        'cached_pages': cached_pages,
        'uncached_pages': uncached_pages,
        'estimated_hours': estimated_hours
    }

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description="OCR 进度检查和加速工具")
    parser.add_argument('--check', action='store_true', help='检查 OCR 缓存状态')
    parser.add_argument('--estimate', action='store_true', help='估算剩余处理时间')
    parser.add_argument('--clean', action='store_true', help='清理无效缓存')
    parser.add_argument('--clean-all', action='store_true', help='清理所有缓存（慎用）')
    parser.add_argument('--data-dir', type=str, default='./data', help='数据目录路径')
    
    args = parser.parse_args()
    
    if args.check:
        check_ocr_cache(args.data_dir)
    elif args.clean or args.clean_all:
        clean_ocr_cache(args.data_dir, args.clean_all)
    elif args.estimate:
        estimate_processing_time(args.data_dir)
    else:
        # 默认显示所有信息
        print("\n使用 --help 查看可用选项\n")
        check_ocr_cache(args.data_dir)
        estimate_processing_time(args.data_dir)
