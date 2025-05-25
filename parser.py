import clang.cindex
import os
import json
import re

# 配置Clang库路径
clang.cindex.Config.set_library_path('/opt/homebrew/opt/llvm/lib')
PROJECT_ROOT = '/Users/ormete/PycharmCode/gpt3.5_api/cParser/zopfli'


class CParser:
    def __init__(self, project_root=PROJECT_ROOT):
        self.project_root = project_root
        self.index = clang.cindex.Index.create()
        self.compile_args = [
            '-I/opt/homebrew/opt/llvm/include',
            '-I/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include',
            '-I/usr/include',
            '-x', 'c',
            '-std=c11',
        ]

    def parse_file(self, filepath):
        """解析单个文件，返回其架构信息"""
        tu = self.index.parse(filepath, args=self.compile_args)
        if not tu:
            return None

        tokens = list(tu.get_tokens(extent=tu.cursor.extent))

        # 提取各类结构
        structs = self._extract_structs(tu.cursor, filepath, tokens)
        defines = self._extract_macros(filepath)
        typedefs = self._extract_typedefs(tu.cursor, filepath, tokens)

        result = {
            "structs": self._list_to_dict(structs, "signature"),
            "defines": self._list_to_dict(defines, "name"),
            "typedefs": self._list_to_dict(typedefs, "name"),
            "functions": self._extract_functions(tu.cursor, filepath, tokens),
            "fields": self._extract_fields(tu.cursor, filepath, tokens),
        }
        return result

    def parse_project(self):
        """解析整个项目，保存架构信息到JSON文件"""
        files = self._collect_files()
        project_arch = {}
        for file in files:
            rel_path = os.path.relpath(file, self.project_root)
            arch = self.parse_file(file)
            if arch:
                project_arch[rel_path] = arch

        with open('project_architecture.json', 'w') as f:
            json.dump(project_arch, f, indent=4)
        print("✅ 架构信息提取完成，保存至 project_architecture.json")
        return project_arch

    def _collect_files(self):
        """收集项目中所有C和头文件"""
        files = []
        for dirpath, _, filenames in os.walk(self.project_root):
            for f in filenames:
                if f.endswith(".c") or f.endswith(".h"):
                    files.append(os.path.join(dirpath, f))
        return files

    def _is_project_file(self, filepath):
        """判断文件是否为项目内部文件"""
        if not filepath:
            return False
        filepath = os.path.abspath(filepath)
        return filepath.startswith(os.path.abspath(self.project_root))

    def _is_in_file(self, cursor, filepath):
        """判断游标是否位于指定文件中"""
        return cursor.location.file and os.path.samefile(str(cursor.location.file), filepath)

    def _is_in_project(self, cursor):
        """判断游标是否位于项目内"""
        return cursor.location.file and self._is_project_file(str(cursor.location.file.name))

    def _get_preceding_comment(self, tokens, target_line):
        """获取行前注释"""
        comment = ""
        for i in range(len(tokens) - 1):
            if tokens[i].kind == clang.cindex.TokenKind.COMMENT:
                if tokens[i + 1].location.line == target_line:
                    comment = tokens[i].spelling.strip()
        return comment

    def _get_source_text(self, cursor):
        """获取游标范围内的源代码文本"""
        extent = cursor.extent
        tokens = list(cursor.translation_unit.get_tokens(extent=extent))
        return "".join(tok.spelling + (" " if tok.kind != clang.cindex.TokenKind.PUNCTUATION else "") for tok in tokens)

    def _list_to_dict(self, items, key_field):
        """将列表转换为字典，使用指定字段作为键"""
        return {item[key_field]: item for item in items}

    def _get_qualified_name(self, cursor):
        """获取项目内游标的限定名称"""
        if not cursor.location.file or not self._is_in_project(cursor):
            return None

        rel_path = os.path.relpath(cursor.location.file.name, self.project_root).replace(".c", "").replace(".h", "")

        if cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL:
            # 函数：包含参数类型
            args = ', '.join([arg.type.spelling for arg in cursor.get_arguments()])
            return f"{rel_path}::{cursor.spelling}({args})"
        elif cursor.kind in [
            clang.cindex.CursorKind.VAR_DECL,
            clang.cindex.CursorKind.TYPEDEF_DECL,
            clang.cindex.CursorKind.STRUCT_DECL,
        ]:
            # 其他类型：文件::名称
            return f"{rel_path}::{cursor.spelling}"

        return None

    def _get_method_name(self, cursor):
        """获取方法名称（不含文件路径）"""
        if not cursor.location.file or not self._is_in_project(cursor):
            return None

        if cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL:
            return f"{cursor.spelling}({', '.join([arg.type.spelling for arg in cursor.get_arguments()])})"

        return None

    def _extract_field_full_text(self, cursor, tokens, field_name):
        """提取字段的完整文本，修复指针和逗号问题"""
        start_line = cursor.extent.start.line
        same_line_tokens = [t for t in tokens if t.location.line == start_line]

        # 分析这一行
        type_tokens = []
        var_tokens_list = []
        current_var_tokens = []
        found_variable = False

        for token in same_line_tokens:
            if token.kind == clang.cindex.TokenKind.PUNCTUATION and token.spelling == ',':
                if current_var_tokens:
                    var_tokens_list.append(current_var_tokens)
                    current_var_tokens = []
                found_variable = False
            elif token.kind == clang.cindex.TokenKind.PUNCTUATION and token.spelling == ';':
                if current_var_tokens:
                    var_tokens_list.append(current_var_tokens)
            elif not found_variable and token.spelling != '*':
                # 还没遇到变量
                type_tokens.append(token)
            else:
                current_var_tokens.append(token)
                found_variable = True

        # 查找指定字段
        for var_tokens in var_tokens_list:
            names = [t.spelling for t in var_tokens if t.kind == clang.cindex.TokenKind.IDENTIFIER]
            if field_name in names:
                # 处理 * 号
                star_prefix = ""
                body_tokens = []
                for t in var_tokens:
                    if t.spelling == '*':
                        star_prefix += '*'
                    else:
                        body_tokens.append(t.spelling)

                # 构造完整文本
                type_text = " ".join(t.spelling for t in type_tokens if t.spelling not in ['*', '&'])
                full_text = f"{type_text} {star_prefix}{' '.join(body_tokens)};"
                full_text = ' '.join(full_text.split())  # 清理多余空格
                return full_text

        # 如果分析失败，返回默认文本
        return self._get_source_text(cursor)

    def _extract_macros(self, filepath):
        """提取文件中的宏定义，支持多行宏和特殊格式"""
        macros = []

        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        # 使用正则表达式匹配宏定义
        # 匹配 #define 后面的宏名称，处理包含参数的宏
        macro_pattern = re.compile(r'^\s*#define\s+([A-Za-z0-9_]+(?:\([^)]*\))?)(?:\s+(.*))?$', re.MULTILINE)

        lines = content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 检查是否是宏定义起始行
            if line.startswith('#define'):
                # 提取宏名和初始值
                match = macro_pattern.match(line)
                if match:
                    macro_name = match.group(1).strip()
                    macro_value = match.group(2) or ""

                    # 收集完整的宏定义文本
                    full_text = line
                    j = i + 1
                    while j < len(lines) and lines[j - 1].endswith('\\'):
                        full_text += '\n' + lines[j]
                        # 去掉行尾反斜杠后添加到宏值中
                        if macro_value:
                            macro_value += '\n' + lines[j].strip()
                        else:
                            macro_value = lines[j].strip()
                        j += 1

                    # 去掉行尾的反斜杠
                    macro_value = macro_value.replace('\\\n', '\n')

                    macros.append({
                        "name": macro_name,
                        "signature": macro_name,
                        "value": macro_value,
                        "full_text": full_text
                    })

                    i = j - 1  # 更新索引到宏的最后一行

            i += 1

        return macros

    def _collect_dependencies(self, cursor, filepath, self_qualified_name=None):
        """收集节点的依赖关系（函数、宏、typedef、struct）"""
        dependencies = {}

        # 提取所有宏名
        macro_names = [m["name"] for m in self._extract_macros(filepath)]

        # 提取源码文本（用于匹配宏）
        source = self._get_source_text(cursor)

        # 遍历AST查找引用
        for c in cursor.walk_preorder():
            ref = c.referenced
            if not ref:
                continue  # 没有引用对象

            # 忽略编译器内建函数
            if ref.spelling and ref.spelling.startswith('__builtin_'):
                continue

            location = ref.location
            if location.file and self._is_project_file(str(location.file.name)):
                qualified_name = self._get_qualified_name(ref)
                ref_kind = ref.kind

                # 如果 qualified_name 是 None，跳过
                if not qualified_name:
                    continue

                # 如果引用自己或自己的内部字段，跳过
                if self_qualified_name and (
                        qualified_name == self_qualified_name or
                        qualified_name.startswith(self_qualified_name + "::")
                ):
                    continue

                # 根据引用对象类型，区分依赖类型
                if ref_kind.name == "FUNCTION_DECL":
                    dep_type = "functions"
                elif ref_kind.name == "TYPEDEF_DECL":
                    dep_type = "typedefs"
                elif ref_kind.name == "STRUCT_DECL":
                    dep_type = "structs"
                else:
                    continue  # 其他类型跳过

                dependencies[qualified_name] = {
                    "qualified_name": qualified_name,
                    "type": dep_type
                }

        # 检查宏依赖
        for macro in macro_names:
            # 获取宏定义所在的文件名（不含后缀）
            file_basename = os.path.basename(filepath)
            file_name = os.path.splitext(file_basename)[0]
            if macro and re.search(r'\b' + re.escape(macro) + r'\b', source):
                dependencies[f"{file_name}::{macro}"] = {
                    "return_type": "macro",
                    "qualified_name": f"{file_name}::{macro}",
                    "type": "defines"
                }

        return dependencies

    def _collect_function_dependencies(self, cursor, filepath):
        """收集函数的依赖关系，更详细的版本"""
        dependencies = {}

        def is_non_local_reference(ref):
            """判断是否为非局部引用"""
            # 首先检查ref是否为None
            if ref is None:
                return False

            # 忽略编译器内建函数
            if ref.spelling and ref.spelling.startswith('__builtin_'):
                return False

            # 其他检查保持不变
            if not self._is_in_project(ref):
                return False

            if ref.kind == clang.cindex.CursorKind.FUNCTION_DECL:
                return ref != cursor

            if ref.kind == clang.cindex.CursorKind.VAR_DECL:
                return ref.semantic_parent.kind == clang.cindex.CursorKind.TRANSLATION_UNIT

            if ref.kind in [clang.cindex.CursorKind.STRUCT_DECL, clang.cindex.CursorKind.TYPEDEF_DECL]:
                return True

            return False

        # 遍历AST查找引用
        for c in cursor.walk_preorder():
            ref = c.referenced
            if is_non_local_reference(ref):
                qualified = self._get_qualified_name(ref)
                if qualified and qualified not in dependencies:
                    # 根据引用类型确定依赖类型
                    if ref.kind == clang.cindex.CursorKind.FUNCTION_DECL:
                        dep_type = "functions"
                        return_type = ref.result_type.spelling
                    elif ref.kind == clang.cindex.CursorKind.VAR_DECL:
                        dep_type = "fields"
                        return_type = ref.type.spelling
                    elif ref.kind == clang.cindex.CursorKind.STRUCT_DECL:
                        dep_type = "structs"
                        return_type = ref.type.spelling
                    elif ref.kind == clang.cindex.CursorKind.TYPEDEF_DECL:
                        # 如果底层类型是结构体，归为structs
                        underlying_type = ref.underlying_typedef_type
                        if underlying_type.get_declaration().kind == clang.cindex.CursorKind.STRUCT_DECL:
                            dep_type = "structs"
                        else:
                            dep_type = "typedefs"
                        return_type = ref.type.spelling
                    else:
                        dep_type = "unknown"
                        return_type = ref.type.spelling

                    dependencies[qualified] = {
                        "return_type": return_type,
                        "qualified_name": qualified,
                        "type": dep_type
                    }

        # 添加宏依赖
        macro_names = [m["name"] for m in self._extract_macros(filepath)]
        source = self._get_source_text(cursor)
        for macro in macro_names:
            # 获取宏定义所在的文件名（不含后缀）
            file_basename = os.path.basename(filepath)
            file_name = os.path.splitext(file_basename)[0]
            if macro and re.search(r'\b' + re.escape(macro) + r'\b', source):
                dependencies[f"{file_name}::{macro}"] = {
                    "return_type": "macro",
                    "qualified_name": f"{file_name}::{macro}",
                    "type": "defines"
                }

        return dependencies

    def _extract_fields(self, cursor, filepath, tokens):
        """提取全局变量和常量字段"""
        fields = {}

        for c in cursor.walk_preorder():
            if c.kind == clang.cindex.CursorKind.VAR_DECL and self._is_in_file(c, filepath):
                # 只处理翻译单元级别的变量（全局变量）
                if c.semantic_parent.kind == clang.cindex.CursorKind.TRANSLATION_UNIT:
                    name = c.spelling

                    # 确定变量类型（const、static或global）
                    if "const" in c.type.spelling:
                        kind = "const"
                    elif c.storage_class == clang.cindex.StorageClass.STATIC:
                        kind = "static"
                    else:
                        kind = "global"

                    fields[name] = {
                        "signature": f"{c.type.spelling} {name}",
                        "description": self._get_preceding_comment(tokens, c.extent.start.line),
                        "full_text": self._extract_field_full_text(c, tokens, name),
                        "kind": kind,
                        "dependencies": self._collect_dependencies(c, filepath, self._get_qualified_name(c))
                    }

        return fields

    def _extract_functions(self, cursor, filepath, tokens):
        """提取函数信息"""
        methods = {}

        def process_function(cursor):
            nonlocal methods
            if cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL and self._is_in_project(cursor):
                # 仅处理当前文件的函数
                if cursor.location.file.name != filepath:
                    return

                qualified = self._get_method_name(cursor)
                if qualified:
                    methods[qualified] = {
                        "signature": f"{cursor.result_type.spelling} {cursor.spelling}({', '.join([a.type.spelling for a in cursor.get_arguments()])})",
                        "description": self._get_preceding_comment(tokens, cursor.extent.start.line),
                        "dependencies": self._collect_function_dependencies(cursor, filepath),
                        "full_text": self._get_source_text(cursor)
                    }

            # 递归处理子节点
            for c in cursor.get_children():
                process_function(c)

        process_function(cursor)
        return methods

    def _extract_structs(self, cursor, filepath, tokens, seen=None):
        """提取结构体信息"""
        if seen is None:
            seen = set()

        structs = []

        def process_struct(cursor):
            nonlocal structs

            if cursor.kind == clang.cindex.CursorKind.STRUCT_DECL and self._is_in_file(cursor,
                                                                                       filepath) and cursor.is_definition():
                struct_name = cursor.displayname

                # 避免重复处理
                if struct_name in seen:
                    return
                seen.add(struct_name)

                struct_source = self._get_source_text(cursor)
                struct = {
                    "signature": struct_name,
                    "description": self._get_preceding_comment(tokens, cursor.extent.start.line),
                    "file": os.path.relpath(cursor.location.file.name, self.project_root),
                    "fields": [],
                    "full_text": struct_source,
                    "dependencies": self._collect_dependencies(cursor, filepath, self._get_qualified_name(cursor))
                }

                # 提取结构体字段
                for c in cursor.get_children():
                    if c.kind == clang.cindex.CursorKind.FIELD_DECL:
                        struct["fields"].append({
                            "signature": f"{c.type.spelling} {c.spelling}",
                            "description": self._get_preceding_comment(tokens, c.extent.start.line)
                        })

                structs.append(struct)

            # 递归处理子节点
            for c in cursor.get_children():
                process_struct(c)

        process_struct(cursor)
        return structs

    def _extract_typedefs(self, cursor, filepath, tokens):
        """提取类型定义信息"""
        typedefs = []

        def process_typedef(cursor):
            nonlocal typedefs

            if (
                    cursor.kind == clang.cindex.CursorKind.TYPEDEF_DECL
                    and self._is_in_file(cursor, filepath)
                    # 排除结构体定义内的typedef
                    and not any(gc.kind == clang.cindex.CursorKind.STRUCT_DECL for gc in cursor.get_children())
            ):
                name = cursor.spelling
                signature = self._get_source_text(cursor)
                comment = self._get_preceding_comment(tokens, cursor.extent.start.line)

                typedefs.append({
                    "name": name,
                    "signature": signature,
                    "description": comment,
                    "full_text": signature,
                    "dependencies": self._collect_dependencies(cursor, filepath, self._get_qualified_name(cursor))
                })

            # 递归处理子节点
            for c in cursor.get_children():
                process_typedef(c)

        process_typedef(cursor)
        return typedefs


def main():
    parser = CParser()
    parser.parse_project()


if __name__ == '__main__':
    main()