import json
import logging
from typing import Dict, Any, List, Optional
from .gpt_client import GPT

logger = logging.getLogger(__name__)

class FunctionSummarizer:
    """函数总结生成器，使用两个AI模型进行生成和验证"""
    
    def __init__(self, api_key: str, output_file: str = "function_summaries.json"):
        """初始化函数总结生成器
        
        Args:
            api_key: OpenAI API密钥
            output_file: 输出文件路径
        """
        self.generator = GPT(api_key, model_name="gpt-4")  # 生成AI
        self.validator = GPT(api_key, model_name="gpt-4")  # 验证AI
        self.output_file = output_file
        self.current_batch = {}
        self.batch_count = 0
        
        # 状态跟踪
        self.processed_functions = self._load_processed_functions()
        self.state_file = output_file + '.state'
        
        # 生成器提示模板
        self.generator_prompt = """你是一个专门分析C/Rust函数的专家。请按照以下格式对给定的函数进行分析和总结：

{
    "function_name": "函数名称",
    "file_name": "所属文件名",
    "functionality": {
        "description": "函数的主要功能描述",
        "input": ["输入参数1说明", "输入参数2说明", ...],
        "output": "返回值说明"
    },
    "implementation_logic": "1. 第一步：xxx\n2. 第二步：xxx\n3. 第三步：xxx",
    "dependencies": {
        "structs": [
            {
                "name": "结构体名称",
                "signature": "完整的Rust结构体签名"
            }
        ],
        "functions": [
            {
                "name": "函数名称",
                "signature": "完整的Rust函数签名"
            }
        ],
        "types": [
            {
                "name": "类型名称",
                "signature": "完整的Rust类型定义"
            }
        ]
    }
}

请分析以下函数并生成总结：

[FUNCTION_CODE]

注意：
1. 确保所有依赖项的签名都是完整的Rust格式
2. implementation_logic使用编号列表形式，每步都要说明具体实现和使用的依赖项
3. 保持JSON格式的严格性
"""

        # 验证器提示模板
        self.validator_prompt = """你是一个专门验证函数总结的专家。请检查以下函数总结是否符合要求：

[SUMMARY]

原始函数：

[FUNCTION_CODE]

请检查以下几点并返回JSON格式的验证结果：

{
    "is_valid": true/false,
    "issues": [
        {
            "type": "错误类型",
            "description": "具体问题描述",
            "suggestion": "修改建议"
        }
    ],
    "missing_dependencies": [
        {
            "type": "依赖类型",
            "name": "依赖名称",
            "reason": "为什么认为缺失"
        }
    ],
    "incorrect_implementations": [
        {
            "step": "有问题的步骤",
            "issue": "具体问题",
            "correction": "正确的描述"
        }
    ]
}

验证重点：
1. 功能描述是否准确完整
2. 实现逻辑是否清晰且包含所有关键步骤
3. 依赖项是否完整且签名正确
4. JSON格式是否有效
"""

    def _load_processed_functions(self) -> Dict[str, set]:
        """加载已处理的函数列表
        
        Returns:
            Dict[str, set]: 文件名到函数名集合的映射
        """
        processed = {}
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for file_name, funcs in data.items():
                        processed[file_name] = set(funcs.keys())
                logger.info(f"已加载{sum(len(s) for s in processed.values())}个已处理的函数")
            except Exception as e:
                logger.error(f"加载已处理函数列表失败: {e}")
        return processed

    def _is_function_processed(self, file_name: str, func_name: str) -> bool:
        """检查函数是否已经处理过
        
        Args:
            file_name: 文件名
            func_name: 函数名
            
        Returns:
            bool: 是否已处理
        """
        return file_name in self.processed_functions and func_name in self.processed_functions[file_name]

    def _mark_function_processed(self, file_name: str, func_name: str):
        """标记函数为已处理
        
        Args:
            file_name: 文件名
            func_name: 函数名
        """
        if file_name not in self.processed_functions:
            self.processed_functions[file_name] = set()
        self.processed_functions[file_name].add(func_name)

    def generate_summary(self, function_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成函数总结
        
        Args:
            function_data: 包含函数信息的字典
            
        Returns:
            生成的函数总结
        """
        # 准备函数代码
        function_code = function_data.get("full_text", "")
        if not function_code:
            logger.error("未提供函数代码")
            return {}
            
        # 生成总结
        prompt = self.generator_prompt.replace("[FUNCTION_CODE]", function_code)
        try:
            response = self.generator.ask([{"role": "user", "content": prompt}])
            summary = json.loads(response)
        except Exception as e:
            logger.error(f"生成总结失败: {e}")
            return {}
            
        # 验证总结
        validation_prompt = self.validator_prompt.replace(
            "[SUMMARY]", 
            json.dumps(summary, indent=2, ensure_ascii=False)
        ).replace(
            "[FUNCTION_CODE]",
            function_code
        )
        
        try:
            validation_response = self.validator.ask([{"role": "user", "content": validation_prompt}])
            validation_result = json.loads(validation_response)
        except Exception as e:
            logger.error(f"验证总结失败: {e}")
            return summary
            
        # 如果验证发现问题，记录但仍返回原始总结
        if not validation_result.get("is_valid", True):
            logger.warning("总结验证发现问题:")
            for issue in validation_result.get("issues", []):
                logger.warning(f"- {issue['type']}: {issue['description']}")
            for dep in validation_result.get("missing_dependencies", []):
                logger.warning(f"- 缺失依赖: {dep['type']} {dep['name']}")
            for impl in validation_result.get("incorrect_implementations", []):
                logger.warning(f"- 实现问题: {impl['step']} - {impl['issue']}")
                
        return summary
        
    def process_function(self, file_name: str, func_name: str, func_data: Dict[str, Any]):
        """处理单个函数并添加到批次中
        
        Args:
            file_name: 文件名
            func_name: 函数名
            func_data: 函数数据
        """
        # 检查是否已处理
        if self._is_function_processed(file_name, func_name):
            logger.info(f"跳过已处理的函数: {file_name}::{func_name}")
            return
            
        logger.info(f"正在总结函数: {file_name}::{func_name}")
        summary = self.generate_summary(func_data)
        
        if summary:
            if file_name not in self.current_batch:
                self.current_batch[file_name] = {}
            self.current_batch[file_name][func_name] = summary
            self.batch_count += 1
            
            # 标记为已处理
            self._mark_function_processed(file_name, func_name)
            
            # 每10个函数保存一次
            if self.batch_count >= 10:
                self.save_current_batch()
                
    def save_current_batch(self):
        """保存当前批次的总结"""
        try:
            # 如果文件已存在，先读取现有内容
            existing_data = {}
            if os.path.exists(self.output_file):
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    
            # 合并现有数据和新数据
            for file_name, funcs in self.current_batch.items():
                if file_name not in existing_data:
                    existing_data[file_name] = {}
                existing_data[file_name].update(funcs)
                
            # 保存合并后的数据
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)
                
            logger.info(f"已保存{self.batch_count}个函数的总结")
            
            # 清空当前批次
            self.current_batch = {}
            self.batch_count = 0
            
        except Exception as e:
            logger.error(f"保存总结失败: {e}")
        
    def process_architecture(self, architecture_file: str):
        """处理整个架构文件
        
        Args:
            architecture_file: 架构文件路径
        """
        try:
            # 加载架构文件
            with open(architecture_file, 'r', encoding='utf-8') as f:
                architecture_data = json.load(f)
                
            # 统计总函数数量
            total_functions = sum(
                len(content.get("functions", {}))
                for content in architecture_data.values()
            )
            processed_count = sum(
                len(funcs) for funcs in self.processed_functions.values()
            )
            
            logger.info(f"总函数数量: {total_functions}")
            logger.info(f"已处理函数数量: {processed_count}")
            logger.info(f"待处理函数数量: {total_functions - processed_count}")
                
            # 处理所有函数
            for file_name, file_content in architecture_data.items():
                if "functions" not in file_content:
                    continue
                    
                for func_name, func_data in file_content["functions"].items():
                    self.process_function(file_name, func_name, func_data)
                    
            # 保存剩余的函数
            if self.batch_count > 0:
                self.save_current_batch()
                
            logger.info("架构文件处理完成！")
            logger.info(f"本次共处理了{sum(len(funcs) for funcs in self.processed_functions.values()) - processed_count}个新函数")
            
        except Exception as e:
            logger.error(f"处理架构文件时出错: {e}")

if __name__ == "__main__":
    import os
    import sys
    
    # 检查命令行参数
    if len(sys.argv) < 2:
        print("用法: python function_summarizer.py <architecture_file> [output_file]")
        sys.exit(1)
        
    # 获取参数
    architecture_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'function_summaries.json'
    
    # 获取API密钥
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("错误: 未设置OPENAI_API_KEY环境变量")
        sys.exit(1)
        
    # 创建总结器并处理
    summarizer = FunctionSummarizer(api_key, output_file)
    summarizer.process_architecture(architecture_file) 