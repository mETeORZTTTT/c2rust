import re
import json

class TextExtractor:
    @staticmethod
    def extract_json(text):
        """从文本中提取JSON对象"""
        
        def simple_fix_json_control_chars(json_text):
            """简单修复JSON字符串中的控制字符"""
            def fix_string_value(match):
                string_content = match.group(1)
                # 修复未转义的控制字符
                fixed_content = string_content.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                return f'"{fixed_content}"'
            
            # 匹配JSON字符串值
            pattern = r'"((?:[^"\\]|\\.)*)"'
            return re.sub(pattern, fix_string_value, json_text)
        
        # 方法1：检查markdown的json代码块
        json_code_block_pattern = r'```json\s*([\s\S]*?)\s*```'
        json_block_match = re.search(json_code_block_pattern, text)
        if json_block_match:
            json_content = json_block_match.group(1).strip()
            
            # 直接尝试解析
            try:
                parsed = json.loads(json_content)
                if isinstance(parsed, dict) and ("result" in parsed or "rust_code" in parsed):
                    return parsed
            except json.JSONDecodeError:
                pass
            
            # 修复控制字符后尝试解析
            try:
                fixed_json = simple_fix_json_control_chars(json_content)
                parsed = json.loads(fixed_json)
                if isinstance(parsed, dict) and ("result" in parsed or "rust_code" in parsed):
                    return parsed
            except json.JSONDecodeError:
                pass
        
        # 方法2：尝试直接解析整个文本
        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, dict) and ("result" in parsed or "rust_code" in parsed):
                return parsed
        except json.JSONDecodeError:
            pass
        
        # 方法3：修复控制字符后解析整个文本
        try:
            fixed_text = simple_fix_json_control_chars(text.strip())
            parsed = json.loads(fixed_text)
            if isinstance(parsed, dict) and ("result" in parsed or "rust_code" in parsed):
                return parsed
        except json.JSONDecodeError:
            pass
        
        # 方法4：找到完整的JSON对象
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1 and start < end:
                json_text = text[start:end+1]
            
            # 直接尝试解析
            try:
                parsed = json.loads(json_text)
                if isinstance(parsed, dict) and ("result" in parsed or "rust_code" in parsed):
                    return parsed
            except json.JSONDecodeError:
                pass
            
            # 修复控制字符后尝试解析
            try:
                fixed_json = simple_fix_json_control_chars(json_text)
                parsed = json.loads(fixed_json)
                if isinstance(parsed, dict) and ("result" in parsed or "rust_code" in parsed):
                    return parsed
            except json.JSONDecodeError:
                pass
        
        return None
    
    @staticmethod
    def extract_code_block(text, language="rust"):
        """从文本中提取代码块"""
        pattern = rf"```{language}([\s\S]*?)```"
        matches = re.findall(pattern, text)
        
        if matches:
            return matches[0].strip()
        
        # 如果没有找到指定语言的代码块，尝试查找任意代码块
        # 但要排除json代码块，因为那不是真正的代码
        pattern = r"```(?!json\b)(\w*)\s*([\s\S]*?)```"
        matches = re.findall(pattern, text)
        
        if matches:
            # 返回代码内容，不包含语言标识符
            for lang, code_content in matches:
                if code_content.strip():
                    return code_content.strip()
        
        # 如果仍然没有找到，尝试不带语言标识符的代码块
        pattern = r"```([\s\S]*?)```"
        matches = re.findall(pattern, text)
        
        if matches:
            for match in matches:
                # 跳过以"json"开头的代码块内容
                content = match.strip()
                if not content.startswith('json\n') and not content.startswith('json '):
                    return content
        
        # 检查文本是否包含JSON格式（如果包含，说明这是JSON响应而非代码）
        if "{" in text and "}" in text and ("rust_code" in text or "result" in text):
            # 这很可能是JSON响应而非代码，返回空而不是整个文本
            return ""
        
        # 如果没有找到任何代码块，尝试提取看起来像代码的部分
        # 查找以Rust关键字开头的内容
        clean_text = re.sub(r'^.*?(?=\b(pub|fn|struct|enum|impl|const|static|type|use|let)\b)', '', text, flags=re.DOTALL)
        
        # 如果清理后的文本仍然包含JSON特征，返回空
        if clean_text and ("{" in clean_text and "}" in clean_text and ("rust_code" in clean_text or "result" in clean_text)):
            return ""
            
        return clean_text.strip() if clean_text.strip() else "" 