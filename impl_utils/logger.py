import os
import logging
from datetime import datetime

# 配置日志
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

class Logger:
    """日志工具类，支持文件和控制台输出"""
    
    @staticmethod
    def setup():
        """设置根日志器"""
        logging.basicConfig(level=logging.INFO)
        
    @staticmethod
    def get_logger(name, console_output=True, file_output=True):
        """获取指定名称的日志器
        
        Args:
            name: 日志器名称
            console_output: 是否输出到控制台
            file_output: 是否输出到文件
            
        Returns:
            配置好的日志器
        """
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False  # 禁止日志向上传播到root logger
        
        # 确保处理器不会重复添加
        if not logger.handlers:
            # 文件输出
            if file_output:
                file_handler = logging.FileHandler(
                    os.path.join(LOG_DIR, f"{name}.log"),
                    encoding="utf-8",
                    mode='w'  # 使用'w'模式，每次运行覆盖之前的日志
                )
                file_handler.setLevel(logging.DEBUG)
                formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            
            # 控制台输出
            if console_output:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.INFO)
                formatter = logging.Formatter('%(levelname)s: %(message)s')
                console_handler.setFormatter(formatter)
                logger.addHandler(console_handler)
                
        return logger 