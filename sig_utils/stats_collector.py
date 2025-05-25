from datetime import datetime

class ConversionStats:
    def __init__(self):
        self.total_items = 0
        self.success_count = 0
        self.fail_count = 0
        self.skipped_count = 0  # 跳过的项目数量（如头文件保护宏）
        self.by_type = {}  # 按类型统计
        self.error_types = {}  # 错误类型统计
        self.rounds_data = []  # 每次转换的轮数
        self.start_time = datetime.now()
        self.samples = {
            "success": [],  # 成功样本
            "failure": [],  # 失败样本
            "skipped": []   # 跳过样本
        }
    
    def record_start(self, item_id, kind):
        """记录开始处理一个项目"""
        self.total_items += 1
        if kind not in self.by_type:
            self.by_type[kind] = {"total": 0, "success": 0, "fail": 0, "skipped": 0}
        self.by_type[kind]["total"] += 1
    
    def record_success(self, item_id, kind, rounds, example=None, is_skipped=False):
        """记录一次成功转换"""
        self.success_count += 1
        self.by_type[kind]["success"] += 1
        
        if is_skipped:
            self.skipped_count += 1
            self.by_type[kind]["skipped"] += 1
            if example and len(self.samples["skipped"]) < 5:
                self.samples["skipped"].append({
                    "id": item_id,
                    "kind": kind,
                    "reason": "头文件保护宏",
                    "example": example
                })
        else:
            self.rounds_data.append(rounds)
            if example and len(self.samples["success"]) < 5:
                self.samples["success"].append({
                    "id": item_id,
                    "kind": kind,
                    "rounds": rounds,
                    "example": example
                })
    
    def record_failure(self, item_id, kind, error_type, example=None):
        """记录一次失败转换"""
        self.fail_count += 1
        self.by_type[kind]["fail"] += 1
        
        if error_type not in self.error_types:
            self.error_types[error_type] = 0
        self.error_types[error_type] += 1
        
        if example and len(self.samples["failure"]) < 5:
            self.samples["failure"].append({
                "id": item_id,
                "kind": kind,
                "error_type": error_type,
                "example": example
            })
    
    def generate_report(self, gpt_stats=None):
        """生成统计报告"""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        # 计算平均轮数（仅考虑非跳过项）
        avg_rounds = sum(self.rounds_data) / len(self.rounds_data) if self.rounds_data else 0
        
        report = {
            "总体统计": {
                "开始时间": self.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "结束时间": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "总耗时(秒)": duration,
                "总项目数": self.total_items,
                "成功转换": self.success_count,
                "成功率": f"{(self.success_count / self.total_items * 100):.2f}%" if self.total_items else "0%",
                "跳过项目": self.skipped_count,
                "失败转换": self.fail_count,
                "平均轮数": f"{avg_rounds:.2f}"
            },
            "类型统计": {},
            "错误类型": self.error_types,
            "样例": self.samples
        }
        
        # 添加按类型统计
        for kind, stats in self.by_type.items():
            success_rate = (stats["success"] / stats["total"] * 100) if stats["total"] else 0
            report["类型统计"][kind] = {
                "总数": stats["total"],
                "成功": stats["success"],
                "跳过": stats["skipped"],
                "失败": stats["fail"],
                "成功率": f"{success_rate:.2f}%"
            }
        
        # 添加API使用信息
        if gpt_stats:
            report["API使用"] = gpt_stats
        
        return report 