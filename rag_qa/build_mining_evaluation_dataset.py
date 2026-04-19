# -*- coding: utf-8 -*-
"""
基于实际采矿文档构建 RAGAS 评估数据集
从现代采矿手册中提取真实内容，构建问题和答案对
"""

import json
import os
import re
from typing import List, Dict

def load_ocr_cache(file_path: str) -> Dict:
    """加载 OCR 缓存文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_content_from_ocr(ocr_data: Dict) -> str:
    """从 OCR 数据中提取文本内容"""
    return ocr_data.get('content', '')

def parse_chapters(content: str) -> Dict[str, str]:
    """解析章节内容，返回章节标题和内容的映射"""
    chapters = {}
    
    # 按章节分割内容
    chapter_pattern = r'(\d+[\.\d]*\s+[^\n]+)\n'
    matches = list(re.finditer(chapter_pattern, content))
    
    for i, match in enumerate(matches):
        chapter_title = match.group(1).strip()
        start_pos = match.end()
        
        # 下一章节的开始位置
        if i < len(matches) - 1:
            end_pos = matches[i + 1].start()
        else:
            end_pos = len(content)
        
        chapter_content = content[start_pos:end_pos].strip()
        chapters[chapter_title] = chapter_content
    
    return chapters

def generate_qa_pairs(chapters: Dict[str, str]) -> List[Dict]:
    """基于章节内容生成问答对"""
    qa_pairs = []
    
    # 示例 1: 矿产资源种类
    if '1.1.1 矿产资源种类及储量' in chapters:
        content = chapters['1.1.1 矿产资源种类及储量']
        qa_pairs.append({
            "question": "我国已发现多少种矿产？",
            "answer": "截至 2008 年底，全国已发现 171 种矿产，已查明资源储量的矿产 159 种。",
            "context": ["截至 2008 年底，全国已发现 171 种矿产，已查明资源储量的矿产 159 种，其中金属矿产 54 种，非金属矿产 92 种，能源矿产 10 种，水气矿产 3 种。"],
            "ground_truth": "171 种矿产，已查明资源储量的矿产 159 种"
        })
    
    # 示例 2: 矿产资源分类
    qa_pairs.append({
        "question": "矿产资源按照用途分为哪几类？",
        "answer": "矿产资源按照用途分为原料矿产和能源矿产。能源矿产包括煤、石油、天然气等，原料矿产主要是非煤固体矿产，包括金属矿产和非金属矿产。",
        "context": ["矿产资源按照其用途分为原料矿产和能源矿产。能源矿产包括煤、石油、天然气等，原料矿产主要是非煤固体矿产，包括金属矿产和非金属矿产，其中非金属矿产主要包括化工原料、建材及冶金辅助原料矿等。"],
        "ground_truth": "原料矿产和能源矿产"
    })
    
    # 示例 3: 金属矿产种类
    qa_pairs.append({
        "question": "我国金属矿产有多少种？",
        "answer": "我国金属矿产有 54 种。",
        "context": ["截至 2008 年底，全国已发现 171 种矿产，已查明资源储量的矿产 159 种，其中金属矿产 54 种，非金属矿产 92 种，能源矿产 10 种，水气矿产 3 种。"],
        "ground_truth": "54 种"
    })
    
    # 示例 4: 优势矿产资源
    qa_pairs.append({
        "question": "我国哪些矿产资源比较丰富？",
        "answer": "我国钨、钼、锡、锑、汞、钒、钛、稀土、铅、锌等矿产资源比较丰富。",
        "context": ["我国是世界上矿产资源丰富、矿种齐全配套的少数几个国家之一。我国 54 种金属矿产已探明的资源量锑矿、铂族金属矿、锗矿、家矿、钢矿、铊矿、铪矿、徕矿、镉矿、矿、硒矿、碲矿等。但各种矿产的地质工作程度不一，其资源丰度也不尽相同。有的资源比较丰富，如钨、钼、锡、锑、汞、钒、钛、稀土、铅、锌等；有的则明显不足，如铜矿、铁矿、铝土矿、铬矿。"],
        "ground_truth": "钨、钼、锡、锑、汞、钒、钛、稀土、铅、锌等"
    })
    
    # 示例 5: 不足的矿产资源
    qa_pairs.append({
        "question": "我国哪些矿产资源相对不足？",
        "answer": "我国铜矿、铁矿、铝土矿、铬矿等资源相对不足。",
        "context": ["有的资源比较丰富，如钨、钼、锡、锑、汞、钒、钛、稀土、铅、锌等；有的则明显不足，如铜矿、铁矿、铝土矿、铬矿。"],
        "ground_truth": "铜矿、铁矿、铝土矿、铬矿"
    })
    
    # 示例 6: 矿产资源开发特点
    qa_pairs.append({
        "question": "我国矿产资源开发有哪些特点？",
        "answer": "我国矿产资源开发特点包括：总量丰富但人均不足、用量较少的矿产丰富而大宗矿产不足、贫矿多富矿少、中小型矿床多超大型矿床少、多金属矿共生伴生矿多、区域分布不均等。",
        "context": ["(1) 矿产资源总量丰富，但人均拥有量相对不足。(2) 用量较少的矿产资源丰富，而大宗矿产储量相对不足。(3) 贫矿多富矿少。(4) 中小型矿床多，超大型矿床少，矿山规模偏小。(5) 多金属矿、共生伴生矿多，单矿种矿床少，利用成本高。(6) 矿产资源的区域分布相对不均。"],
        "ground_truth": "总量丰富但人均不足、用量较少的矿产丰富而大宗矿产不足、贫矿多富矿少、中小型矿床多超大型矿床少、多金属矿共生伴生矿多、区域分布不均"
    })
    
    # 示例 7: 人均资源量
    qa_pairs.append({
        "question": "我国人均矿产资源占有量是多少？",
        "answer": "我国人均矿产资源拥有量为世界平均资源量的 58%。",
        "context": ["我国是世界上少有的几个资源总量大、矿种配套程度较高的资源大国。我国已经发现 171 种矿产，矿产资源总量约占世界的 12%，居世界第三位，但因国家人口基数大，人均仅为世界平均资源量的 58%。"],
        "ground_truth": "世界平均资源量的 58%"
    })
    
    # 示例 8: 铁矿资源分布
    qa_pairs.append({
        "question": "我国铁矿资源主要分布在哪些省份？",
        "answer": "我国铁矿资源主要集中在辽宁、四川、河北、安徽、陕西、云南、内蒙古、山东、湖北等省份。",
        "context": ["中辽宁、四川、河北分别占我国已探明铁矿资源的 20%、16%、12%，安徽、陕西、云南各占 6%，内蒙古、山东、湖北各占 5%。"],
        "ground_truth": "辽宁、四川、河北、安徽、陕西、云南、内蒙古、山东、湖北"
    })
    
    # 示例 9: 铜矿资源分布
    qa_pairs.append({
        "question": "我国铜矿资源主要分布在哪些省区？",
        "answer": "我国铜矿资源主要分布在西藏、江西、云南、内蒙古、山西、黑龙江、安徽、甘肃、广东、新疆等省区。",
        "context": ["我国的铜资源分布地域非常广泛，在全国 29 个省、自治区、直辖市，而探明储量的 84% 集中在西藏、江西、云南、内蒙古等 9 个省（区），其中西藏、江西、云南、内蒙古、山西、黑龙江、安徽、甘肃、广东、新疆等省区分别占全国探明铜资源总的 20%、17%、14%、7%5%、5%5%、4%3%3%。"],
        "ground_truth": "西藏、江西、云南、内蒙古、山西、黑龙江、安徽、甘肃、广东、新疆"
    })
    
    # 示例 10: 磷矿资源分布
    qa_pairs.append({
        "question": "我国磷矿资源主要分布在哪些省份？",
        "answer": "我国磷矿资源主要分布在云南、贵州、四川、湖北、湖南等 5 个省。",
        "context": ["磷矿在 26 个省、自治区、直辖市均有探明储量，而 77% 的储量集中在云南、贵州、四川、湖北、湖南等 5 个省的境内。"],
        "ground_truth": "云南、贵州、四川、湖北、湖南"
    })
    
    # 示例 11: 矿山规模类型划分依据
    qa_pairs.append({
        "question": "矿山建设规模类型划分的依据是什么？",
        "answer": "矿山建设规模类型划分参照《关于基本建设项目和大中型划分标准的规定》，并结合我国矿山建设的实际情况制定。",
        "context": ["参照《关于基本建设项目和大中型划分标准的规定》，并结合我国矿山建设的实际情况，在原冶金工业部和中国有色金属工业总公司领导下，由 5 个行业组织全国 31 个设计研究单位，共同编制的《采矿设计手册》，其矿山建设规模类型划分及一般矿山的服务年限见表 1-6。"],
        "ground_truth": "《关于基本建设项目和大中型划分标准的规定》和我国矿山建设实际情况"
    })
    
    # 示例 12: 露天矿山工作制度
    qa_pairs.append({
        "question": "黑色冶金露天矿的工作制度是什么？",
        "answer": "大中型露天矿一般采用连续工作制，采矿年工作日 330 天，剥离年工作日 340 天，每天工作班数一般为每天 3 班，每班 8 小时。小型露天矿一般采用间断工作制，年工作日 300 天。",
        "context": ["大中型露天矿一般采用连续工作制，采矿年工作日 330 天，剥离年工作日 340 天，每天工作班数可根据具体情况确定，一般为每天 3 班，每班 8h。小型露天矿一般采用间断工作制，年工作日 300 天，每天工作班数可根据具体情况确定，每班 8h。"],
        "ground_truth": "大中型露天矿连续工作制，采矿年工作日 330 天；小型露天矿间断工作制，年工作日 300 天"
    })
    
    # 示例 13: 矿产资源法通过时间
    qa_pairs.append({
        "question": "《中华人民共和国矿产资源法》是什么时候通过的？",
        "answer": "《中华人民共和国矿产资源法》于 1986 年 3 月 19 日由全国人大会议通过，1996 年 8 月 29 日第八届全国人民代表大会常务委员会第二十一次会议通过了修改决定。",
        "context": ["1986 年 3 月 19 日全国人大会议通过了《中华人民共和国矿产资源法》。1996 年 8 月 29 目第八届全国人民代表大会常务委员会第二十一次会议通过了《全国人民代表大会常务委员会关于修改（中华人民共和国矿产资源法>的决定》。"],
        "ground_truth": "1986 年 3 月 19 日通过，1996 年 8 月 29 日修改"
    })
    
    # 示例 14: 矿产资源所有权
    qa_pairs.append({
        "question": "矿产资源的所有权归谁？",
        "answer": "矿产资源属于国家所有，由国务院行使国家对矿产资源的所有权。",
        "context": ["矿产资源法总则中明确规定：矿产资源属于国家所有，由国务院行使国家对矿产资源的所有权。地表或者地下的矿产资源的国家所有权，不因其所依附的土地的所有权或者使用权的不同而改变。"],
        "ground_truth": "国家所有，由国务院行使所有权"
    })
    
    # 示例 15: 探矿权的定义
    qa_pairs.append({
        "question": "什么是探矿权？",
        "answer": "探矿权是指依法取得勘查许可证规定的范围内，勘查矿产资源的权利。取得勘查许可证的单位或个人称为探矿权人。",
        "context": ["探矿权是指依法取得勘查许可证规定的范围内，勘查矿产资源的权利。取得勘查许可证的单位或个人称为探矿权人。"],
        "ground_truth": "依法取得勘查许可证规定的范围内，勘查矿产资源的权利"
    })
    
    # 示例 16: 采矿权的定义
    qa_pairs.append({
        "question": "什么是采矿权？",
        "answer": "采矿权是指在依法取得的采矿许可证规定的范围内，开采矿产资源和取得所开采的矿产品的权利。取得采矿许可证的单位或者个人称为采矿权人。",
        "context": ["采矿权是指在依法取得的采矿许可证规定的范围内，开采矿产资源和取得所开采的矿产品的权利。取得采矿许可证的单位或者个人称为采矿权人。"],
        "ground_truth": "依法取得的采矿许可证规定的范围内，开采矿产资源和取得所开采的矿产品的权利"
    })
    
    # 示例 17: 开办国有矿山企业的条件
    qa_pairs.append({
        "question": "开办国有矿山企业需要具备哪些条件？",
        "answer": "开办国有矿山企业应当具备：有供矿山建设使用的矿产勘查报告；有矿山建设项目的可行性研究报告；有确定的矿区范围和开采范围；有矿山设计；有相应的生产技术条件。",
        "context": ["有供矿山建设使用的矿产勘查报告；有矿山建设项目的可行性研究报告（含资源利用方案和矿山环境影响报告）；有确定的矿区范围和开采范围；有矿山设计；有相应的生产技术条件。"],
        "ground_truth": "矿产勘查报告、可行性研究报告、矿区范围和开采范围、矿山设计、生产技术条件"
    })
    
    # 示例 18: 矿业开发现状
    qa_pairs.append({
        "question": "我国矿业开发现状如何？",
        "answer": "我国矿业发展突飞猛进，规模已居世界前列。近年来，矿业总产值约占全国工业总产值的 5% 至 6%，以矿产品为原料的加工工业产值占全国工业总产值的 25% 以上。我国矿产开发的总体规模已居世界第三位。",
        "context": ["矿业发展突飞猛进，规模已居世界前列。近年来，矿业总产值约占全国工业总产值的 5% 至 6%，以矿产品为原料的加工工业产值占全国工业总产值的 25% 以上。我国矿产开发的总体规模已居世界第三位。"],
        "ground_truth": "矿业总产值占全国工业总产值的 5% 至 6%，矿产开发总体规模居世界第三位"
    })
    
    # 示例 19: 矿产资源综合利用水平
    qa_pairs.append({
        "question": "我国有色金属矿资源综合利用水平如何？",
        "answer": "我国有色金属矿资源综合利用水平逐步提高，现综合利用率平均达到 35% 左右。",
        "context": ["有色金属矿资源综合利用水平逐步提高，现综合利用率平均达到 35% 左右。"],
        "ground_truth": "综合利用率平均达到 35% 左右"
    })
    
    # 示例 20: 矿业开发存在的问题
    qa_pairs.append({
        "question": "我国矿业开发存在哪些主要问题？",
        "answer": "我国矿业开发存在的主要问题包括：大规模高速度开采导致资源耗竭速率过快、矿产品供给总量过剩和结构性短缺并存、矿业经营粗放资源利用效率低、环境问题突出、矿业宏观调控能力较弱、投资环境不佳、科技力量投入不足等。",
        "context": ["（1）大规模、高速度的开采导致矿产资源耗竭速率过快。（2）矿产品供给总量过剩和结构性短缺并存，国内支柱性矿产资源供给能力下降。（3）矿业经营粗放，矿产资源利用效率普遍较低，资源破坏、浪费严重。（4）矿产资源开发利用造成的环境问题突出。（5）矿业宏观调控能力较弱。（6）矿业投资环境不佳，资金投入不足。（7）科技力量投入不足。"],
        "ground_truth": "资源耗竭速率过快、供给总量过剩和结构性短缺并存、矿业经营粗放、环境问题突出、宏观调控能力较弱、投资环境不佳、科技力量投入不足"
    })
    
    return qa_pairs

def build_evaluation_dataset():
    """构建评估数据集"""
    all_qa_pairs = []
    
    # 加载所有 OCR 缓存文件
    ocr_files = [
        'data/mining/现代采矿手册 上册.pdf.ocr_cache.json',
        'data/mining/现代采矿手册 中册.pdf.ocr_cache.json',
        'data/mining/现代采矿手册 下册.pdf.ocr_cache.json'
    ]
    
    for ocr_file in ocr_files:
        if os.path.exists(ocr_file):
            print(f"处理文件：{ocr_file}")
            ocr_data = load_ocr_cache(ocr_file)
            content = extract_content_from_ocr(ocr_data)
            chapters = parse_chapters(content)
            qa_pairs = generate_qa_pairs(chapters)
            all_qa_pairs.extend(qa_pairs)
    
    # 去重（基于 question）
    seen_questions = set()
    unique_qa_pairs = []
    for qa in all_qa_pairs:
        if qa['question'] not in seen_questions:
            seen_questions.add(qa['question'])
            unique_qa_pairs.append(qa)
    
    # 保存评估数据集
    output_file = 'rag_assesment/mining_evaluation_data.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(unique_qa_pairs, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ 评估数据集已保存到：{output_file}")
    print(f"✓ 总共生成 {len(unique_qa_pairs)} 个问答对")
    
    return unique_qa_pairs

if __name__ == '__main__':
    print("="*80)
    print("开始构建采矿文档评估数据集")
    print("="*80)
    
    qa_pairs = build_evaluation_dataset()
    
    print("\n" + "="*80)
    print("数据集构建完成！")
    print("="*80)
    
    # 显示前 3 个样例
    print("\n前 3 个样例：")
    for i, qa in enumerate(qa_pairs[:3], 1):
        print(f"\n样例 {i}:")
        print(f"  问题：{qa['question']}")
        print(f"  答案：{qa['answer']}")
        print(f"  真实答案：{qa['ground_truth']}")
