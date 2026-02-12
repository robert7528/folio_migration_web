#!/usr/bin/env python3
"""
FOLIO Migration Tools 任務分析工具 (Python 版)
功能: 分析和顯示 FOLIO migration tasks 的參數定義
"""

import re
import sys
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# 顏色定義
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color

# 設定
# 任務檔案所在路徑 (可從環境變數覆寫)
TASKS_DIR = Path(os.environ.get(
    'TASKS_BASE_PATH',
    '/root/migration_repo_template/.venv/lib64/python3.13/site-packages/folio_migration_tools/migration_tasks'
))

# 基礎參數定義
BASE_PARAMS = {
    'AbstractTaskConfiguration': [
        ('name', 'str', '必填', '任務名稱'),
        ('migration_task_type', 'str', '必填', '任務類型 (migrationTaskType)'),
        ('ecs_tenant_id', 'str', "''", 'ECS tenant ID'),
    ],
    'MarcTaskConfigurationBase': [
        ('files', 'List[FileDefinition]', '必填', 'MARC21 檔案列表'),
        ('create_source_records', 'bool', 'False', '是否保留 MARC 到 SRS'),
        ('hrid_handling', 'HridHandling', "'default'", 'HRID 處理方式'),
        ('deactivate035_from001', 'bool', 'False', '停用 001→035 轉換'),
        ('statistical_codes_map_file_name', 'Optional[str]', "''", '統計代碼映射檔'),
        ('statistical_code_mapping_fields', 'List[str]', '[]', '統計代碼映射欄位'),
    ]
}


class TaskParameter:
    """任務參數資料類別"""
    def __init__(self, name: str, param_type: str, default: str, 
                 title: str = "", description: str = "", alias: str = ""):
        self.name = name
        self.param_type = param_type
        self.default = default
        self.title = title
        self.description = description
        self.alias = alias


class TaskAnalyzer:
    """任務分析器"""
    
    def __init__(self, tasks_dir: Path):
        self.tasks_dir = tasks_dir
    
    def list_tasks(self) -> List[Tuple[str, str, str]]:
        """列出所有任務"""
        tasks = []
        for file_path in self.tasks_dir.glob("*.py"):
            if file_path.name.startswith("__"):
                continue
            
            content = file_path.read_text(encoding='utf-8')
            
            # 找出主要的 Task class
            match = re.search(
                r'^class ([A-Z][a-zA-Z]+(Transformer|Migrator|Poster))\(([A-Za-z]+)\):',
                content,
                re.MULTILINE
            )
            
            if match:
                task_class = match.group(1)
                base_class = match.group(3)
                tasks.append((file_path.name, task_class, base_class))
        
        return sorted(tasks)
    
    def find_task_file(self, task_name: str) -> Optional[Path]:
        """找到任務檔案"""
        for file_path in self.tasks_dir.glob("*.py"):
            content = file_path.read_text(encoding='utf-8')
            if re.search(rf'^class {task_name}[(:|\s]', content, re.MULTILINE):
                return file_path
        return None
    
    def extract_task_params(self, file_path: Path) -> List[TaskParameter]:
        """提取任務特定參數"""
        content = file_path.read_text(encoding='utf-8')
        
        # 找到 TaskConfiguration 類別的開始和結束
        # 結束標記: 下一個非縮排的屬性或方法定義
        config_start_pattern = r'    class TaskConfiguration\([^)]+\):'
        config_start = re.search(config_start_pattern, content)
        
        if not config_start:
            return []
        
        # 從 TaskConfiguration 開始位置往後找
        start_pos = config_start.end()
        remaining_content = content[start_pos:]
        
        # 找到結束位置: 遇到非縮排的內容或特定標記
        # 例如: "    task_configuration:" 或 "    @staticmethod" 或 "    def "
        end_patterns = [
            r'\n    task_configuration:',
            r'\n    @staticmethod',
            r'\n    @classmethod',
            r'\n    def ',
            r'\n    class [A-Z]',  # 另一個類別
        ]
        
        end_pos = len(remaining_content)
        for pattern in end_patterns:
            match = re.search(pattern, remaining_content)
            if match and match.start() < end_pos:
                end_pos = match.start()
        
        config_content = remaining_content[:end_pos]
        params = []
        
        # 使用逐行解析方式
        lines = config_content.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # 匹配參數定義開始: "        param_name: Annotated["
            # 注意: 必須是 8 個空格的縮排 (類別內的屬性)
            param_match = re.match(r'^        (\w+):\s*Annotated\[', line)
            
            if param_match:
                param_name = param_match.group(1)
                
                # 收集完整的參數定義 (可能跨多行)
                param_lines = [line]
                i += 1
                
                # 計算括號平衡
                bracket_count = line.count('[') - line.count(']')
                paren_count = line.count('(') - line.count(')')
                
                # 繼續收集直到找到 "] =" 或括號平衡
                while i < len(lines):
                    current_line = lines[i]
                    param_lines.append(current_line)
                    
                    bracket_count += current_line.count('[') - current_line.count(']')
                    paren_count += current_line.count('(') - current_line.count(')')
                    
                    # 檢查是否結束 (找到 ] = 或 ] (沒有預設值))
                    if re.search(r'\]\s*=', current_line) or (re.search(r'\]$', current_line.strip()) and bracket_count == 0):
                        break
                    
                    i += 1
                
                # 合併完整定義
                full_param = '\n'.join(param_lines)
                
                # 提取類型
                type_match = re.search(r'Annotated\[\s*([^,]+),', full_param)
                param_type = type_match.group(1).strip() if type_match else "unknown"
                
                # 提取預設值
                default_match = re.search(r'\]\s*=\s*(.+?)(?:\s*#|$)', full_param, re.DOTALL)
                if default_match:
                    default_value = default_match.group(1).strip()
                    # 只取第一行,移除多餘空白
                    default_value = default_value.split('\n')[0].strip()
                else:
                    default_value = "必填"
                
                # 提取 Field 資訊
                field_match = re.search(r'Field\((.*)\)', full_param, re.DOTALL)
                
                title = ""
                description = ""
                alias = ""
                
                if field_match:
                    field_content = field_match.group(1)
                    
                    # 提取 title
                    title_match = re.search(r'title\s*=\s*"([^"]*)"', field_content)
                    if title_match:
                        title = title_match.group(1)
                    
                    # 提取 description (處理多行字串)
                    desc_match = re.search(r'description\s*=\s*\(\s*"([^"]*)"', field_content)
                    if not desc_match:
                        desc_match = re.search(r'description\s*=\s*"([^"]*)"', field_content)
                    if desc_match:
                        description = desc_match.group(1)
                    
                    # 提取 alias
                    alias_match = re.search(r'alias\s*=\s*"([^"]*)"', field_content)
                    if alias_match:
                        alias = alias_match.group(1)
                
                params.append(TaskParameter(
                    name=param_name,
                    param_type=param_type,
                    default=default_value,
                    title=title,
                    description=description,
                    alias=alias
                ))
            
            i += 1
        
        return params
    
    def check_inheritance(self, file_path: Path) -> str:
        """檢查 TaskConfiguration 的繼承"""
        content = file_path.read_text(encoding='utf-8')
        
        match = re.search(r'class TaskConfiguration\(([^)]+)\):', content)
        if match:
            base_class = match.group(1)
            if 'MarcTaskConfigurationBase' in base_class:
                return 'MarcTaskConfigurationBase'
            elif 'AbstractTaskConfiguration' in base_class:
                return 'AbstractTaskConfiguration'
        
        return 'AbstractTaskConfiguration'  # 預設


def show_help():
    """顯示幫助訊息"""
    print(f"{Colors.BOLD}FOLIO Migration Tools 任務分析工具 (Python 版){Colors.NC}")
    print("=" * 60)
    print()
    print("使用方式: python3 folio_task_analyzer.py [command] [options]")
    print()
    print(f"{Colors.BOLD}指令:{Colors.NC}")
    print("  list                    列出所有任務類別")
    print("  params <task>           顯示任務的完整參數 (含繼承)")
    print("  config <task>           顯示 TaskConfiguration 原始碼")
    print("  search <keyword>        搜尋關鍵字")
    print("  export <task>           匯出任務參數為 JSON 範本")
    print()
    print(f"{Colors.BOLD}範例:{Colors.NC}")
    print("  python3 folio_task_analyzer.py list")
    print("  python3 folio_task_analyzer.py params BibsTransformer")
    print("  python3 folio_task_analyzer.py search data_import_marc")
    print("  python3 folio_task_analyzer.py export BibsTransformer")


def cmd_list(analyzer: TaskAnalyzer):
    """列出所有任務"""
    print(f"{Colors.BOLD}📋 所有任務類別:{Colors.NC}")
    print()
    print(f"{Colors.BOLD}{'檔案名稱':<40} {'Task Class':<30} {'繼承自':<30}{Colors.NC}")
    print("=" * 100)
    
    tasks = analyzer.list_tasks()
    for filename, task_class, base_class in tasks:
        print(f"{filename:<40} {task_class:<30} {base_class:<30}")


def cmd_params(analyzer: TaskAnalyzer, task_name: str):
    """顯示任務參數"""
    file_path = analyzer.find_task_file(task_name)
    
    if not file_path:
        print(f"{Colors.RED}❌ 找不到任務 class: {task_name}{Colors.NC}")
        print()
        print(f"{Colors.YELLOW}💡 使用 'python3 folio_task_analyzer.py list' 查看所有可用的任務{Colors.NC}")
        return
    
    print(f"{Colors.BOLD}📋 {task_name} 的完整參數列表 (含繼承){Colors.NC}")
    print(f"檔案: {Colors.CYAN}{file_path.name}{Colors.NC}")
    print("=" * 80)
    print()
    
    # 1. 基礎參數
    print(f"{Colors.BOLD}{Colors.GREEN}【基礎參數】來自 AbstractTaskConfiguration:{Colors.NC}")
    for name, ptype, default, desc in BASE_PARAMS['AbstractTaskConfiguration']:
        print(f"  ├─ {name:<30} ({ptype}, 預設 {default:>8})  {desc}")
    print()
    
    # 2. MARC 參數 (如果適用)
    base_class = analyzer.check_inheritance(file_path)
    if base_class == 'MarcTaskConfigurationBase':
        print(f"{Colors.BOLD}{Colors.GREEN}【MARC 參數】來自 MarcTaskConfigurationBase:{Colors.NC}")
        for name, ptype, default, desc in BASE_PARAMS['MarcTaskConfigurationBase']:
            print(f"  ├─ {name:<30} ({ptype}, 預設 {default:>8})  {desc}")
        print()
    
    # 3. 任務特定參數 (過濾掉基礎參數)
    print(f"{Colors.BOLD}{Colors.GREEN}【{task_name} 特定參數】:{Colors.NC}")
    all_params = analyzer.extract_task_params(file_path)
    
    # 定義要過濾的基礎參數名稱
    base_param_names = {'name', 'migration_task_type', 'ecs_tenant_id'}
    
    # 如果是 MARC 任務,也要過濾 MARC 參數
    marc_param_names = {
        'files', 'create_source_records', 'hrid_handling', 
        'deactivate035_from001', 'statistical_codes_map_file_name',
        'statistical_code_mapping_fields'
    }
    
    # 過濾參數
    params = []
    for param in all_params:
        if param.name in base_param_names:
            continue  # 跳過基礎參數
        if base_class == 'MarcTaskConfigurationBase' and param.name in marc_param_names:
            continue  # 跳過 MARC 參數
        params.append(param)
    
    # camelCase 轉換函數
    def to_camel_case(snake_str):
        components = snake_str.split('_')
        return components[0] + ''.join(x.title() for x in components[1:])
    
    if not params:
        print("  (無特定參數,僅使用繼承的參數)")
    else:
        for i, param in enumerate(params):
            # 格式化預設值
            default_display = param.default
            if len(default_display) > 15:
                default_display = default_display[:12] + "..."
            
            # 轉換為 camelCase
            camel_name = to_camel_case(param.name)
            
            # alias 處理邏輯:
            # - 如果 alias 是真正的 camelCase (首字母小寫且無底線),則使用 alias
            # - 如果 alias 仍是 snake_case (如 ils_flavor),則忽略它,使用 camelCase 轉換
            if param.alias and param.alias[0].islower() and '_' not in param.alias:
                # alias 是有效的 camelCase,使用它
                json_name = param.alias
                has_valid_alias = True
            else:
                # alias 無效或不存在,使用自動轉換的 camelCase
                json_name = camel_name
                has_valid_alias = False
            
            # 組合標題
            title_display = param.title
            
            # 判斷是否為最後一個參數
            prefix = "├─" if i < len(params) - 1 else "└─"
            
            # 顯示格式: Python名稱 → JSON名稱
            # 如果有無效的 alias (snake_case),也提示一下
            if param.alias and not has_valid_alias:
                name_display = f"{param.name:<30} {Colors.CYAN}→ JSON: {json_name}{Colors.NC} {Colors.YELLOW}(alias: {param.alias}){Colors.NC}"
            else:
                name_display = f"{param.name:<30} {Colors.CYAN}→ JSON: {json_name}{Colors.NC}"
            
            print(f"  {prefix} {name_display}")
            print(f"  {'│' if i < len(params) - 1 else ' '}  {Colors.BOLD}{title_display}{Colors.NC}")
            print(f"  {'│' if i < len(params) - 1 else ' '}  預設: {default_display}")
            
            # 顯示說明 (完整顯示,不截斷)
            if param.description:
                # 將長說明分成多行
                desc_text = param.description
                max_width = 70
                
                while desc_text:
                    if len(desc_text) <= max_width:
                        line_symbol = "│" if i < len(params) - 1 else " "
                        print(f"  {line_symbol}  {desc_text}")
                        break
                    
                    # 找最後一個空格來斷行
                    cut_point = desc_text[:max_width].rfind(' ')
                    if cut_point == -1:
                        cut_point = max_width
                    
                    line_symbol = "│" if i < len(params) - 1 else " "
                    print(f"  {line_symbol}  {desc_text[:cut_point]}")
                    desc_text = desc_text[cut_point:].lstrip()
    
    print()
    print(f"{Colors.YELLOW}💡 提示:{Colors.NC}")
    print(f"   - Python 變數名稱 (snake_case) → JSON 參數名稱 (camelCase)")
    print(f"   - 使用 'python3 folio_task_analyzer.py export {task_name}' 產生 JSON 範本")
    print(f"   - 使用 'python3 folio_task_analyzer.py config {task_name}' 查看原始程式碼")


def cmd_config(analyzer: TaskAnalyzer, task_name: str):
    """顯示 TaskConfiguration 原始碼"""
    file_path = analyzer.find_task_file(task_name)
    
    if not file_path:
        print(f"{Colors.RED}❌ 找不到任務 class: {task_name}{Colors.NC}")
        return
    
    print(f"{Colors.BOLD}⚙️  {task_name} 的 TaskConfiguration 定義:{Colors.NC}")
    print(f"檔案: {Colors.CYAN}{file_path.name}{Colors.NC}")
    print("=" * 80)
    print()
    
    content = file_path.read_text(encoding='utf-8')
    
    # 提取 TaskConfiguration 類別
    config_pattern = r'(    class TaskConfiguration\([^)]+\):.*?)(?=\n    @|\n    def |\nclass |\Z)'
    match = re.search(config_pattern, content, re.DOTALL)
    
    if match:
        config_code = match.group(1)
        # 限制顯示行數
        lines = config_code.split('\n')[:100]
        print('\n'.join(lines))
    else:
        print("未找到 TaskConfiguration 定義")


def cmd_search(analyzer: TaskAnalyzer, keyword: str):
    """搜尋關鍵字"""
    print(f"{Colors.BOLD}🔍 搜尋關鍵字: {Colors.YELLOW}{keyword}{Colors.NC}")
    print("=" * 80)
    print()
    
    count = 0
    for file_path in analyzer.tasks_dir.glob("*.py"):
        if file_path.name.startswith("__"):
            continue
        
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        matches = []
        for i, line in enumerate(lines, 1):
            if keyword.lower() in line.lower():
                matches.append((i, line.strip()))
        
        if matches:
            print(f"{Colors.BOLD}📄 {file_path.name}:{Colors.NC}")
            for line_num, line_content in matches[:10]:  # 最多顯示 10 個結果
                print(f"  {Colors.CYAN}行{line_num:4}{Colors.NC}: {line_content[:70]}")
            if len(matches) > 10:
                print(f"  ... 還有 {len(matches) - 10} 個結果")
            print()
            count += 1
    
    if count == 0:
        print(f"{Colors.RED}❌ 未找到包含 '{keyword}' 的結果{Colors.NC}")
    else:
        print(f"{Colors.GREEN}✅ 在 {count} 個檔案中找到結果{Colors.NC}")


def cmd_export(analyzer: TaskAnalyzer, task_name: str):
    """匯出 JSON 範本"""
    file_path = analyzer.find_task_file(task_name)
    
    if not file_path:
        print(f"{Colors.RED}❌ 找不到任務 class: {task_name}{Colors.NC}", file=sys.stderr)
        return
    
    params = analyzer.extract_task_params(file_path)
    base_class = analyzer.check_inheritance(file_path)
    
    # 過濾掉重複的基礎參數
    filtered_params = []
    base_param_names = {'name', 'migration_task_type', 'ecs_tenant_id'}
    
    # 如果是 MARC 任務,也要過濾 MARC 參數
    marc_param_names = {
        'files', 'create_source_records', 'hrid_handling',
        'deactivate035_from001', 'statistical_codes_map_file_name',
        'statistical_code_mapping_fields'
    }
    
    for param in params:
        if param.name in base_param_names:
            continue
        if base_class == 'MarcTaskConfigurationBase' and param.name in marc_param_names:
            continue
        filtered_params.append(param)
    
    # camelCase 轉換函數
    def to_camel_case(snake_str):
        components = snake_str.split('_')
        return components[0] + ''.join(x.title() for x in components[1:])
    
    # 智慧預設值生成
    def get_smart_default(param):
        param_name = param.name
        param_type = param.param_type
        
        # FileDefinition 類型
        if param_type == 'FileDefinition' or (param_name.endswith('_file') and param_type != 'str'):
            return '{\n    "file_name": "users.tsv"\n  }'
        
        # 路徑/檔名參數
        if param_name == 'group_map_path':
            return '"user_groups.tsv"'
        elif param_name == 'departments_map_path':
            return '"user_departments.tsv"'
        elif param_name == 'user_mapping_file_name':
            return '"user_mapping.json"'
        elif param_name.endswith('_path'):
            return f'"{param_name.replace("_path", "")}.tsv"'
        elif param_name.endswith('_file_name'):
            return f'"{param_name.replace("_file_name", "")}.json"'
        
        # 整數類型
        if param_type == 'int':
            if 'batch' in param_name or 'size' in param_name:
                return '100'
            return '1'
        
        # 預設
        return f'"<{param_name}>"'
    
    # 生成 JSON
    json_lines = []
    json_lines.append("{")
    json_lines.append(f'  "name": "my_{task_name.lower()}_task",')
    json_lines.append(f'  "migrationTaskType": "{task_name}",')
    
    # 處理所有參數
    for i, param in enumerate(filtered_params):
        # 轉換參數名為 camelCase
        # 只有當 alias 是真正的 camelCase 時才使用,否則使用自動轉換
        if param.alias and param.alias[0].islower() and '_' not in param.alias:
            camel_name = param.alias
        else:
            camel_name = to_camel_case(param.name)
        
        # 決定參數值
        if param.default == "必填":
            # 必填參數 - 給智慧預設值
            value = get_smart_default(param)
        else:
            # 有預設值的參數 - 轉換格式
            value = param.default
            
            # Python → JSON 格式轉換
            if value == 'True':
                value = 'true'
            elif value == 'False':
                value = 'false'
            elif value in ('""', "''"):
                value = '""'
            elif value == '{}':
                value = '{}'
            elif value == '[]':
                value = '[]'
            elif value == 'None':
                value = 'null'
            # 數字保持原樣
            elif value.replace('.', '', 1).replace('-', '', 1).isdigit():
                pass
            # 其他情況加引號
            elif not (value.startswith('"') or value.startswith('{') or 
                     value.startswith('[') or value in ['true', 'false', 'null']):
                value = f'"{value}"'
        
        # 最後一個參數不加逗號
        comma = "," if i < len(filtered_params) - 1 else ""
        json_lines.append(f'  "{camel_name}": {value}{comma}')
    
    json_lines.append("}")
    
    # 輸出
    for line in json_lines:
        print(line)


def main():
    """主程式"""
    if len(sys.argv) < 2:
        show_help()
        return
    
    analyzer = TaskAnalyzer(TASKS_DIR)
    command = sys.argv[1]
    
    if command == "list":
        cmd_list(analyzer)
    
    elif command == "params":
        if len(sys.argv) < 3:
            print(f"{Colors.RED}❌ 請指定任務 class name{Colors.NC}")
            return
        cmd_params(analyzer, sys.argv[2])
    
    elif command == "config":
        if len(sys.argv) < 3:
            print(f"{Colors.RED}❌ 請指定任務 class name{Colors.NC}")
            return
        cmd_config(analyzer, sys.argv[2])
    
    elif command == "search":
        if len(sys.argv) < 3:
            print(f"{Colors.RED}❌ 請指定搜尋關鍵字{Colors.NC}")
            return
        cmd_search(analyzer, sys.argv[2])
    
    elif command == "export":
        if len(sys.argv) < 3:
            print(f"{Colors.RED}❌ 請指定任務 class name{Colors.NC}")
            return
        cmd_export(analyzer, sys.argv[2])
    
    else:
        show_help()


if __name__ == "__main__":
    main()

