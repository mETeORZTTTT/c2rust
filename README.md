# C到Rust代码转换系统

该系统实现了C代码到Rust代码的智能转换，包括函数签名转换、函数摘要生成和函数实现转换。

## 系统组件

系统主要包含以下组件：

1. **函数签名转换**：将C函数签名转换为Rust函数签名
2. **函数摘要生成**：为C函数生成简洁的功能摘要
3. **函数实现转换**：将C函数实现转换为功能等价的Rust实现

## 使用方法

### 1. 函数摘要生成

```bash
python function_summary_generator.py --input <架构文件> --output <输出文件> [--max-items <最大处理数>]
```

参数说明：
- `--input`：包含已转换签名的架构文件路径
- `--output`：输出结果的文件路径
- `--max-items`：最大处理函数数量

### 2. 函数实现转换

```bash
python function_implementer_main.py --input <架构文件> --output <输出文件> [--max-items <最大处理数>]
```

参数说明：
- `--input`：包含函数摘要的架构文件路径
- `--output`：输出结果的文件路径
- `--max-items`：最大处理函数数量
- `--api-key`：OpenAI API密钥（可选）

## 工作流程

完整的C到Rust转换工作流程：

1. 使用libclang解析C代码，获取代码结构和依赖关系
2. 转换C函数签名为Rust函数签名
3. 生成C函数的功能摘要
4. 选择所有依赖都已实现的函数进行实现
5. 验证生成的Rust代码是否编译通过
6. 可选：进行差分模糊测试验证功能等价性

## 转换策略

系统采用以下策略进行代码转换：

1. **依赖优先**：先转换被依赖的函数，再转换依赖它们的函数
2. **功能等价**：保持与原C代码功能一致，但采用更符合Rust风格的实现
3. **错误处理**：使用Rust的错误处理机制代替C的返回码
4. **内存安全**：利用Rust的所有权系统代替手动内存管理

## 特点

- **智能依赖分析**：基于libclang的精确代码分析
- **依赖关系处理**：优先实现被依赖的代码
- **多阶段转换**：签名转换 -> 摘要生成 -> 实现转换
- **编译验证**：确保生成代码可编译
- **错误修复**：自动修复编译错误
- **差分测试**：验证功能等价性

## 注意事项

- 确保正确设置OpenAI API密钥
- 对于大型项目，建议分批次处理函数
- 生成的Rust代码可能需要进一步人工优化

## 特点

- **智能多代理协作**：使用多个大语言模型分别负责转换、审核和仲裁
- **严格的代码审查**：确保生成的Rust代码符合安全性和惯用性标准
- **丰富的C代码分析**：预处理器可以识别复杂结构（函数指针、位域、联合体等）
- **详细的转换记录**：记录每轮转换历史和审核反馈
- **完善的错误处理**：优雅处理API错误、解析错误等异常情况
- **全面的统计报告**：生成详细的转换成功率、错误类型等统计信息

## 安装

1. 克隆仓库：
```
git clone https://github.com/yourusername/c2rust-converter.git
cd c2rust-converter
```

2. 安装依赖：
```
pip install -r requirements.txt
```

3. 设置API密钥：
```
export OPENAI_API_KEY=your_api_key_here
```

## 使用方法

### 命令行使用

转换完整架构文件：
```
python c2rust_converter.py --input project_architecture.json --output converted_arch.json
```

测试模式（只处理前10个项目）：
```
python c2rust_converter.py --input project_architecture.json --max-items 10
```

启用调试日志：
```
python c2rust_converter.py --input project_architecture.json --debug
```

### 在Python代码中使用

单文件转换：
```python
from c2rust_converter import convert_single_code

c_code = """
typedef struct {
    int id;
    char* name;
} User;
"""

result = convert_single_code(c_code, "struct")
if result["success"]:
    print(result["rust_code"])
```

批量处理整个架构文件：
```python
from c2rust_converter import enrich_architecture_with_rust

result = enrich_architecture_with_rust(
    input_path="project_architecture.json",
    output_path="converted_arch.json"
)
print(f"成功率: {result['stats']['总体统计']['成功率']}")
```

### 示例演示

运行演示示例：
```
python c2rust_demo.py
```

## 架构文件格式

该工具处理的架构文件应为JSON格式，包含以下结构：

```json
{
  "file1.c": {
    "structs": {
      "struct_name": {
        "full_text": "struct定义的完整文本",
        "dependencies": {}  // 可选
      }
    },
    "typedefs": { ... },
    "defines": { ... },
    "fields": { ... }
  },
  "file2.c": {
    // 类似结构
  }
}
```

## 日志与输出

- 转换日志保存在`logs/`目录
- 中间结果和最终结果保存在命令行指定的输出路径
- 统计报告保存为`[output]_report.json`

## 自定义与调优

可以通过修改`PromptTemplates`类中的提示来调整转换的行为和风格。主要的提示包括：

- `AGENT1_SYSTEM`: 设置转换专家的基本行为
- `AGENT1_PROMPTS`: 针对不同类型的转换提示
- `AGENT2_SYSTEM`: 设置审核专家的严格程度
- `AGENT3_SYSTEM`: 设置仲裁专家的行为

## 许可证

MIT

## 致谢

该项目使用OpenAI的GPT模型实现，感谢所有为Rust和C社区做出贡献的开发者。 




TODO：
defines typedfes注意有没有函数实现

python3 c2rust_converter_new.py \
  --enable-compile-check \
  --generate-validation \
  --max-items 1000