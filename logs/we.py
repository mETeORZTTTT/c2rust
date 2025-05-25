import json
import sys
from collections import Counter, defaultdict

def count_json_types(json_file):
    # 读取JSON文件
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 初始化统计数据结构
    total_counts = Counter()
    file_type_counts = defaultdict(Counter)
    conversion_status = defaultdict(Counter)
    
    # 遍历文件中的每个项目
    for file_name, file_content in data.items():
        # 遍历每种类型
        for type_name in ["fields", "defines", "typedefs", "structs", "functions"]:
            if type_name in file_content:
                # 统计该类型在当前文件中的数量
                count = len(file_content[type_name])
                total_counts[type_name] += count
                file_type_counts[file_name][type_name] = count
                
                # 统计转换状态（如果有）
                for item_name, item in file_content[type_name].items():
                    status = item.get("conversion_status", "未处理")
                    conversion_status[type_name][status] += 1
    
    # 输出统计结果
    print("=" * 50)
    print("总体统计:")
    for type_name, count in total_counts.items():
        print(f"{type_name}: {count}项")
    print(f"总计: {sum(total_counts.values())}项")
    
    print("\n" + "=" * 50)
    print("各文件类型分布:")
    for file_name, counts in file_type_counts.items():
        total = sum(counts.values())
        if total > 0:
            print(f"\n{file_name} (总计: {total}项):")
            for type_name, count in counts.items():
                print(f"  {type_name}: {count}项")
    
    # 如果有转换状态数据，则输出
    if any(conversion_status.values()):
        print("\n" + "=" * 50)
        print("转换状态统计:")
        for type_name, statuses in conversion_status.items():
            if statuses:
                print(f"\n{type_name}:")
                for status, count in statuses.items():
                    print(f"  {status}: {count}项")

if __name__ == "__main__":
    # 使用命令行参数获取JSON文件路径，默认为merged_architecture.json
    json_file = sys.argv[1] if len(sys.argv) > 1 else "merged_architecture.json"
    count_json_types(json_file)