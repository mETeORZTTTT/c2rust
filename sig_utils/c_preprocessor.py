import re

class CPreprocessor:
    @staticmethod
    def clean_comments(code):
        """清除C代码中的注释"""
        # 清除块注释 /* ... */
        code = re.sub(r'/\*[\s\S]*?\*/', '', code)
        # 清除行注释 // ...
        code = re.sub(r'//.*', '', code)
        return code
    
    @staticmethod
    def normalize_whitespace(code):
        """规范化空白字符"""
        # 将多个空白字符替换为单个空格
        code = re.sub(r'\s+', ' ', code)
        # 在特定标点前后添加空格
        code = re.sub(r'([{};,])', r' \1 ', code)
        # 规范化指针声明
        code = re.sub(r'(\w+)\*', r'\1 *', code)
        # 去除重复空格
        code = re.sub(r' +', ' ', code)
        # 修复括号间距
        code = re.sub(r'\( ', r'(', code)
        code = re.sub(r' \)', r')', code)
        return code.strip()
    
    @staticmethod
    def is_header_guard(text):
        """检测是否为头文件保护宏"""
        # 匹配形如 #define __HEADER_H_ 的宏定义
        header_guard_pattern = r'^\s*#\s*define\s+(_+[A-Z][A-Z0-9_]*_H_*|__[A-Z][A-Z0-9_]*_H__?|[A-Z][A-Z0-9_]*_INCLUDED)(\s.*)?$'
        if re.match(header_guard_pattern, text):
            return True
        return False
    
    @staticmethod
    def classify_macro(text):
        """分类宏定义类型"""
        if CPreprocessor.is_header_guard(text):
            return "header_guard"
        
        # 检测是否为简单的常量定义 #define NAME value
        if re.match(r'^\s*#\s*define\s+[A-Za-z_][A-Za-z0-9_]*\s+[^(].*$', text):
            return "constant"
        
        # 检测是否为函数宏 #define NAME(args) body
        if re.match(r'^\s*#\s*define\s+[A-Za-z_][A-Za-z0-9_]*\s*\(', text):
            return "function_macro"
        
        # 检测条件编译宏
        if re.match(r'^\s*#\s*(if|ifdef|ifndef|elif|else|endif)', text):
            return "conditional"
        
        return "other"
    
    @staticmethod
    def identify_special_constructs(code):
        """识别特殊C语言结构"""
        constructs = {
            "function_pointers": [],
            "bitfields": [],
            "unions": [],
            "arrays": [],
            "nested_structs": [],
            "header_guards": []
        }
        
        # 检测函数指针
        fp_pattern = r'\b(\w+)\s*\(\s*\*\s*(\w+)\s*\)\s*\(([^)]*)\)'
        for match in re.finditer(fp_pattern, code):
            constructs["function_pointers"].append({
                "return_type": match.group(1),
                "name": match.group(2),
                "params": match.group(3),
                "full_text": match.group(0)
            })
        
        # 检测位域
        bf_pattern = r'(\w+)\s*:\s*(\d+)'
        for match in re.finditer(bf_pattern, code):
            constructs["bitfields"].append({
                "name": match.group(1),
                "bits": match.group(2),
                "full_text": match.group(0)
            })
        
        # 检测联合体
        union_pattern = r'union\s*{([^}]*)}'
        for match in re.finditer(union_pattern, code):
            constructs["unions"].append({
                "members": match.group(1).strip(),
                "full_text": match.group(0)
            })
        
        # 检测数组
        array_pattern = r'(\w+)\s+(\w+)\s*\[(\d+)\]'
        for match in re.finditer(array_pattern, code):
            constructs["arrays"].append({
                "type": match.group(1),
                "name": match.group(2),
                "size": match.group(3),
                "full_text": match.group(0)
            })
        
        # 检测嵌套结构体
        nested_pattern = r'struct\s*{([^}]*)}\s*(\w+)'
        for match in re.finditer(nested_pattern, code):
            constructs["nested_structs"].append({
                "members": match.group(1).strip(),
                "name": match.group(2),
                "full_text": match.group(0)
            })
        
        # 检测头文件保护宏
        if CPreprocessor.is_header_guard(code):
            constructs["header_guards"].append({
                "full_text": code.strip()
            })
        
        return constructs
    
    @staticmethod
    def preprocess(code):
        """完整的预处理流程"""
        code = CPreprocessor.clean_comments(code)
        code = CPreprocessor.normalize_whitespace(code)
        special_constructs = CPreprocessor.identify_special_constructs(code)
        
        # 检查是否为头文件保护宏
        is_header_guard = CPreprocessor.is_header_guard(code)
        macro_type = CPreprocessor.classify_macro(code)
        
        return {
            "processed_code": code,
            "special_constructs": special_constructs,
            "is_header_guard": is_header_guard,
            "macro_type": macro_type
        } 