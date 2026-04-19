# -*- coding:utf-8 -*-
"""
测试云雾 API 的 OCR 功能
使用 DashScope 多模态模型进行 OCR 识别
"""
import requests
import base64
import cv2
import numpy as np
from base import Config

conf = Config()

def test_yunwu_ocr():
    print("=" * 70)
    print("云雾 API - OCR 功能测试")
    print("=" * 70)
    
    # 配置信息
    print(f"\nAPI Key: {conf.DASHSCOPE_API_KEY[:20]}...")
    print(f"Base URL: {conf.DASHSCOPE_BASE_URL}")
    
    # 创建测试图片（中英文 + 数字混合）
    img = np.ones((300, 500, 3), dtype=np.uint8) * 255
    cv2.putText(img, '采矿工程测试', (50, 80), 
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 2)
    cv2.putText(img, 'NVIDIA vs Cloud', (50, 150), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    cv2.putText(img, 'OCR 2024 Test', (50, 220), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    
    _, img_base64 = cv2.imencode('.png', img)
    img_base64_str = base64.b64encode(img_base64).decode('utf-8')
    
    headers = {
        'Authorization': f'Bearer {conf.DASHSCOPE_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    # 测试多个支持 OCR 的模型
    models_to_test = [
        {
            "name": "qwen-vl-max",
            "desc": "通义千问 VL Max（当前使用）"
        },
        {
            "name": "qwen-vl-plus",
            "desc": "通义千问 VL Plus"
        },
        {
            "name": "qwen2-vl-7b-instruct",
            "desc": "Qwen2-VL 7B 指令版"
        }
    ]
    
    results = []
    
    for model in models_to_test:
        print(f"\n{'='*70}")
        print(f"测试模型：{model['name']} - {model['desc']}")
        print(f"{'='*70}")
        
        payload = {
            "model": model["name"],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_base64_str}"}
                        },
                        {
                            "type": "text",
                            "text": "请仔细识别图片中的所有文字内容，包括中文、英文和数字。直接返回文字内容，不要其他说明。"
                        }
                    ]
                }
            ],
            "parameters": {
                "temperature": 0.1,
                "max_tokens": 500
            }
        }
        
        try:
            response = requests.post(
                f"{conf.DASHSCOPE_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
                proxies={'http': 'http://127.0.0.1:7897', 'https': 'http://127.0.0.1:7897'}
            )
            
            print(f"响应状态码：{response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                print(f"✅ 识别成功!")
                print(f"识别结果:\n{content}")
                
                # 检查是否识别出关键内容
                has_chinese = any('\u4e00' <= c <= '\u9fff' for c in content)
                has_english = any(c.isalpha() for c in content)
                has_digit = any(c.isdigit() for c in content)
                
                print(f"\n识别质量检查:")
                print(f"  中文：{'✓' if has_chinese else '✗'}")
                print(f"  英文：{'✓' if has_english else '✗'}")
                print(f"  数字：{'✓' if has_digit else '✗'}")
                
                quality_score = sum([has_chinese, has_english, has_digit])
                results.append((model["name"], True, content, quality_score))
                
            else:
                print(f"❌ 失败 ({response.status_code})")
                print(f"错误：{response.text[:200]}")
                results.append((model["name"], False, response.text[:200], 0))
                
        except Exception as e:
            print(f"\n❌ 异常：{str(e)}")
            results.append((model["name"], False, str(e), 0))
    
    # 汇总结果
    print(f"\n{'='*70}")
    print("测试结果汇总")
    print(f"{'='*70}")
    
    success_count = sum(1 for _, success, _, _ in results if success)
    
    for model_name, success, content, score in results:
        status = "✅" if success else "❌"
        print(f"\n{status} {model_name}")
        if success:
            print(f"   识别质量得分：{score}/3")
            print(f"   预览：{content[:80]}...")
    
    print(f"\n总计：{success_count}/{len(models_to_test)} 成功")
    
    if success_count > 0:
        # 找出最佳模型
        best_model = max([(name, score) for name, success, _, score in results if success], 
                        key=lambda x: x[1])
        print(f"\n✅ 推荐模型：{best_model[0]} (得分：{best_model[1]}/3)")
        print(f"\n建议:")
        print(f"1. 在 edu_pdfloader.py 中使用推荐的模型")
        print(f"2. 如果当前 qwen-vl-max 效果最好，保持不变即可")
        return True
    else:
        print(f"\n❌ 所有模型都不可用")
        print(f"\n可能的原因:")
        print(f"1. API Key 余额不足或过期")
        print(f"2. 账户未开通相应模型的权限")
        print(f"3. 云雾 API 服务暂时故障")
        return False

if __name__ == '__main__':
    test_yunwu_ocr()
