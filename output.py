import json
import os
from pathlib import Path


def extract_and_save_rust_code(json_file, output_dir):
    # 创建输出目录（如果不存在）
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 读取JSON文件
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 收集每个模块的代码
    rust_code = {}
    mod_declarations = []

    # 遍历JSON中的每个模块
    for module_name, module_data in data.items():
        module_code = []

        # 添加模块声明和必要的导入
        module_code.append(f"// Generated module: {module_name}")
        module_code.append("use std::io::{self, Write};")
        module_code.append("use std::fs::File;")

        # 处理结构体
        if "structs" in module_data:
            for struct_name, struct_data in module_data["structs"].items():
                if "rust_signature" in struct_data:
                    module_code.append(struct_data["rust_signature"])

        # 处理定义
        if "defines" in module_data:
            for define_name, define_data in module_data["defines"].items():
                if "rust_signature" in define_data:
                    module_code.append(define_data["rust_signature"])

        # 处理类型定义
        if "typedefs" in module_data:
            for typedef_name, typedef_data in module_data["typedefs"].items():
                if "rust_signature" in typedef_data:
                    module_code.append(typedef_data["rust_signature"])

        # 处理字段
        if "fields" in module_data and isinstance(module_data["fields"], dict):
            for field_name, field_data in module_data["fields"].items():
                if "rust_signature" in field_data:
                    module_code.append(field_data["rust_signature"])

        # 处理函数
        if "functions" in module_data:
            for func_name, func_data in module_data["functions"].items():
                if "rust_implementation" in func_data:
                    module_code.append(func_data["rust_implementation"])
                elif "rust_signature" in func_data:
                    module_code.append(func_data["rust_signature"])

        # 如果模块中有代码，保存到对应文件
        if module_code:
            rust_code[module_name] = "\n\n".join(module_code)
            mod_declarations.append(module_name)

    # 创建模块结构和文件
    for module_name, code in rust_code.items():
        # 创建模块目录（如果需要嵌套模块）
        if "::" in module_name:
            parts = module_name.split("::")
            current_path = output_path
            for part in parts[:-1]:
                current_path = current_path / part
                current_path.mkdir(exist_ok=True)
                # 创建mod.rs文件以声明子模块
                mod_rs_path = current_path / "mod.rs"
                if not mod_rs_path.exists():
                    with open(mod_rs_path, 'w', encoding='utf-8') as f:
                        f.write("pub mod {};\n".format(parts[-1]))
            # 创建最终的rs文件
            file_path = current_path / f"{parts[-1]}.rs"
        else:
            # 单层模块，直接在src目录下创建文件
            file_path = output_path / f"{module_name}.rs"

        # 写入代码到文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(code)
        print(f"已写入文件: {file_path}")

    # 创建lib.rs文件，引入所有顶层模块
    top_modules = set()
    for module_name in mod_declarations:
        top_name = module_name.split("::")[0]
        top_modules.add(top_name)

    lib_content = [f"pub mod {module_name};" for module_name in sorted(top_modules)]

    with open(output_path / "lib.rs", 'w', encoding='utf-8') as f:
        f.write("\n".join(lib_content))
    print(f"已写入文件: {output_path / 'lib.rs'}")


if __name__ == "__main__":
    json_file = "merged_architecture_result2.json"  # 你的JSON文件路径
    output_dir = "/Users/ormete/CProjects/genann-4dd67e42bc99c611c0ec4fa18b27ca257d022c73/src"
    extract_and_save_rust_code(json_file, output_dir)