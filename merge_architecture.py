import json
import os

PROJECT_ARCH_PATH = "project_architecture.json"

def load_architecture(path):
    with open(path, 'r') as f:
        return json.load(f)

def merge_by_signature(list1, list2):
    """合并两个列表，按 signature 去重"""
    sigs = {item['signature']: item for item in list1}
    for item in list2:
        if item['signature'] not in sigs:
            sigs[item['signature']] = item
    return list(sigs.values())

def list_to_dict_by_field(items, key_field):
    """将列表转为 dict，以指定字段为 key"""
    return {item[key_field]: item for item in items if key_field in item}

def normalize_qualified_name(name):
    """将依赖项中的 .h 或 .c 去掉"""
    if "::" in name:
        filename, rest = name.split("::", 1)
        base = os.path.splitext(filename)[0]
        return f"{base}::{rest}"
    return name

def merge_functions(src_funcs, header_funcs):
    """合并函数：保留源文件为主，补充 description"""
    result = {}
    for key, val in header_funcs.items():
        norm_key = normalize_qualified_name(key)
        result[norm_key] = val

    for key, val in src_funcs.items():
        norm_key = normalize_qualified_name(key)
        if norm_key in result:
            if not val.get("description") and result[norm_key].get("description"):
                val["description"] = result[norm_key]["description"]
        result[norm_key] = val

    # 统一 dependencies 中的函数名
    final_result = {}
    for key, val in result.items():
        if "dependencies" in val:
            new_deps = {}
            for dep_key, dep_val in val["dependencies"].items():
                norm_dep_key = normalize_qualified_name(dep_key)
                dep_val["qualified_name"] = norm_dep_key
                new_deps[norm_dep_key] = dep_val
            val["dependencies"] = new_deps
        final_result[key] = val

    return final_result

def merge_fields(fields1, fields2):
    """合并 fields 字典，保留字段名为 key"""
    merged = fields1.copy()
    for name, field in fields2.items():
        if name not in merged:
            merged[name] = field
        else:
            # 若有相同字段名，补充 description 或 full_text
            if not merged[name].get("description") and field.get("description"):
                merged[name]["description"] = field["description"]
            if not merged[name].get("full_text") and field.get("full_text"):
                merged[name]["full_text"] = field["full_text"]
    return merged

def merge_files(data):
    merged = {}
    processed = set()

    for file in list(data.keys()):
        base, ext = os.path.splitext(file)
        if file in processed:
            continue

        c_file = f"{base}.c"
        h_file = f"{base}.h"

        c_arch = data.get(c_file, {})
        h_arch = data.get(h_file, {})

        merged_entry = {}

        # description
        merged_entry["description"] = c_arch.get("description") or h_arch.get("description", "")

        # structs（先合并为列表，再转回 dict）
        structs_list = merge_by_signature(
            list(c_arch.get("structs", {}).values()),
            list(h_arch.get("structs", {}).values())
        )
        merged_entry["structs"] = list_to_dict_by_field(structs_list, "signature")

        # defines（先合并为列表，再转回 dict）
        defines_list = merge_by_signature(
            list(c_arch.get("defines", {}).values()),
            list(h_arch.get("defines", {}).values())
        )
        merged_entry["defines"] = list_to_dict_by_field(defines_list, "name")

        # typedefs（先合并为列表，再转回 dict）
        typedefs_list = merge_by_signature(
            list(c_arch.get("typedefs", {}).values()),
            list(h_arch.get("typedefs", {}).values())
        )
        merged_entry["typedefs"] = list_to_dict_by_field(typedefs_list, "signature")

        # functions
        merged_entry["functions"] = merge_functions(
            c_arch.get("functions", {}),
            h_arch.get("functions", {})
        )

        # fields
        merged_entry["fields"] = merge_fields(
            c_arch.get("fields", {}),
            h_arch.get("fields", {})
        )

        merged[base] = merged_entry
        processed.update({c_file, h_file})

    return merged

def main():
    data = load_architecture(PROJECT_ARCH_PATH)
    merged_data = merge_files(data)
    with open("merged_architecture.json", "w") as f:
        json.dump(merged_data, f, indent=4)
    print("✅ 合并完成，保存至 merged_architecture.json")

if __name__ == "__main__":
    main()