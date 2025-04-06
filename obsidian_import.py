#!/usr/bin/env python3

# 📁 Obsidian 导入需求:
# (Copilot 必须在编辑代码时同步这些需求，如果需求发生变化！)
#
# 此脚本处理从 Notion 导出的目录，其中包含多个 Markdown 文件
# （文件名格式为："DocumentName UID.md"）。如果 Markdown 文件引用了附件，
# 它们存储在一个单独的目录中（目录名称与 Markdown 文件相同）。可能有多个附件。
# 如果文档名称相同，则使用 UID 来区分它们。
#
# 🎯 目标:
# - 📄 从 Markdown 文件名中移除 UID（如果没有重复文件）。
# - 🗂️ 将所有附件整合到一个 "Resource" 目录中。
# - ✏️ 根据 Markdown 文件名重命名附件。如果有多个附件，
#   在名称后附加序列号。
# - 🖼️ 如果 Markdown 文件仅引用一个图片，则保持图片名称与文档名称相同，
#   不添加序列号。
# - 🔄 更新 Markdown 文件中的引用以反映新的附件路径。
# - 🏷️ 根据用户定义的规则处理并转换 Markdown 文件中的元数据。
#   - ✅ 根据配置文件中定义的规则验证元数据。
#   - 🛠️ 修改元数据键或值，追加额外内容，或删除元数据条目。
#   - 📋 记录未映射的元数据以供审查。
# - 🧹 清理已处理的 Markdown 文件及其对应的附件目录。
#
# 📋 步骤:
# 1) 🏷️ 处理 Markdown 文件中的元数据：
#    - ✅ 根据用户定义的规则验证元数据。
#    - 🛠️ 根据规则转换元数据键或值。
#    - 📋 在 `unmapped_metadata` 字典中记录未映射的元数据以供审查。
# 2) 🔍 搜索 Markdown 文件中引用的附件并将其移动到 "Resource" 目录：
#    - 🖼️ 如果只有一个附件，将其重命名为与 Markdown 文件名相同且不带序列号。
#    - 📚 如果有多个附件，在名称后附加序列号。
#    - 🔄 维护旧附件路径到新路径的映射 (`path_mapping`) 以更新引用。
#    - 🗑️ 如果附件目录中的文件数量与 Markdown 文件中的引用数量一致，
#      创建清理该附件目录的任务。
# 3) 🔄 更新 Markdown 文件以反映新的附件路径：
#    - 📄 使用 `path_mapping` 替换 Markdown 内容中的旧路径为新路径。
#    - 包括行号、原始文本和更新后的文本以更新链接。
# 4) ✏️ 重命名 Markdown 文件以移除 UID（如果没有重复文件）：
#    - 📄 在单独的行中显示源路径和目标路径以便于比较。
# 5) 🧹 清理已处理的 Markdown 文件及其对应的附件目录：
#    - 🗑️ 在处理后删除原始 Markdown 文件及其附件目录。
# 6) 📊 扫描后打印总结任务的统计信息。
# 7) ❓ 在执行任务列表之前提示用户确认。
# 8) 🔄 如果在扫描期间检测到重复名称，附加序列号以解决冲突。
#    确保 Markdown 文件与其附件之间的一致性。
# 9) 📝 在执行任务后生成总结报告。

# 🏷️ 关于元数据的说明:
# 元数据是 Markdown 文件中的字典数据，格式为 "meta name: meta value"。
# 每个元数据占一行，通常出现在文件的前十行内。
# 多个元数据条目之间没有空行。
# 元数据部分通常通过空行或 "---" 行与内容的其余部分分隔。

# 元数据处理类型和操作:
# 1) "retain" - 保留元数据，不做任何更改。
#    - 如果 "retain" 是唯一的操作，则元数据将被跳过，不做任何更改。
#    - 如果同时存在 "retain" 和 "delete"，"delete" 优先，元数据将被删除。
# 2) "delete" - 完全删除元数据条目。
#    - 此操作优先级最高，如果存在，将覆盖其他操作。
# 3) "rename" - 更改元数据键名，同时保留值。
# 4) "modify_value" - 使用直接映射或正则表达式模式转换元数据值。
#    - 直接映射：用预定义的映射替换特定值。
#    - 正则映射：使用正则表达式匹配并替换值。
#    - "modify_value" 在 "append_after" 和 "rename" 之前应用。
# 5) "append_after" - 在现有元数据值后添加文本。
#
# 未映射的元数据:
# - 不符合配置中任何规则的元数据值将被记录以供审查。
# - 这些未映射的值存储在字典 (`unmapped_metadata`) 中以供进一步分析。

import os
import re
import shutil
import argparse
import sys  # Add this import for sys.argv
from collections import defaultdict
from enum import Enum
from pathlib import Path
import time
from urllib.parse import quote, unquote
import yaml
import datetime  # Added for timestamping log entries
import shutil  # For getting terminal size
import logging

#############################################################
# LOGGING FUNCTION
#############################################################

# Define log level constants first
LOG_LEVEL_ERROR = "ERR"
LOG_LEVEL_FLOW = "FLW"
LOG_LEVEL_ACTION = "ACT"
LOG_LEVEL_DEBUG = "DBG"

class TaskType(Enum):
    """Enum defining different types of tasks that can be performed during the import process."""
    RENAME_MD = "RENAME_MD"
    MOVE_ATTACHMENT = "MOVE_ATTACHMENT"
    UPDATE_ATTACH_REF = "UPDATE_ATTACH_REF"
    TRANSFORM_METADATA = "TRANSFORM_METADATA"
    MAP_METADATA = "MAP_METADATA"
    CLEANUP = "CLEANUP"

# 定义日志级别
LOG_LEVELS = {
    LOG_LEVEL_ERROR: logging.ERROR,       # 异常：流程中逻辑冲突和程序异常
    LOG_LEVEL_FLOW: 25,                   # 流程：函数入口点和步骤类函数
    LOG_LEVEL_ACTION: 15,                 # 动作：添加任务，执行动作等实质性动作
    LOG_LEVEL_DEBUG: logging.DEBUG,       # 调试：详细调试信息
}

# 注册自定义日志级别
logging.addLevelName(25, "ACTION")
logging.addLevelName(15, "FLOW")

def debug(message, level, config):
    """
    统一的调试和日志记录函数。

    参数:
        message (str): 要记录的消息
        level (str): 消息的级别（error, action, flow, debug）
        config (dict): 配置字典，控制日志和标准输出的级别
    """
    if config is None:
        config = {}

    # 获取日志和标准输出的级别
    log_level = LOG_LEVELS.get(config.get("log_level", LOG_LEVEL_ACTION), logging.NOTSET)
    stdout_level = LOG_LEVELS.get(config.get("stdout_level", LOG_LEVEL_FLOW), logging.NOTSET)

    # 为不同日志级别定义emoji
    level_emojis = {
        LOG_LEVEL_ERROR: "❌ ",
        LOG_LEVEL_ACTION: "⚡ ",
        LOG_LEVEL_FLOW: "🔄 ",
        LOG_LEVEL_DEBUG: "🔍 "
    }

    # 构建日志消息
    log_message = f"{level_emojis.get(level, '')}{message}"

    # 打印到标准输出
    if LOG_LEVELS[level] >= stdout_level:
        print(log_message)

    # 写入日志文件
    log_file_handle = config.get("log_file_handle")
    if log_file_handle and LOG_LEVELS[level] >= log_level:
        try:
            log_file_handle.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {log_message}\n")
            log_file_handle.flush()  # 确保日志立即写入文件
        except Exception as e:
            print(f"❌ Error writing to log file: {e}")

def initialize_log_file(config):
    """
    初始化日志文件。如果启用了 --reset 参数，则清空日志文件。
    如果启用了 --log 参数但未指定文件名，则使用默认文件名。

    参数:
        config (dict): 包含日志设置的配置字典
    """
    if config.get("log") and not config.get("log_file"):
        config["log_file"] = "obsidian_import.log"

    if config.get("reset_log", False) and config.get("log_file"):
        try:
            if config.get("reset_log"):
                config["log_file_handle"] = open(config["log_file"], "w")  # Overwrite mode
                print(f"✅ Log file {config['log_file']} reset successfully.")
            else:
                config["log_file_handle"] = open(config["log_file"], "a")  # Append mode
                print(f"✅ Log file {config['log_file']} opened for appending.")
            debug("Log file reset by user request", LOG_LEVEL_ACTION, config)
        except Exception as e:
            print(f"❌ Error resetting log file: {e}")

def close_log_file(config):
    """
    关闭日志文件句柄。

    参数:
        config (dict): 配置字典
    """
    log_file_handle = config.get("log_file_handle")
    if log_file_handle:
        try:
            log_file_handle.close()
            print(f"✅ Log file {config['log_file']} closed successfully.")
        except Exception as e:
            print(f"❌ Error closing log file: {e}")
            
#############################################################
# PROGRESS BAR FUNCTION
#############################################################
def display_progress_bar(current, total, description=""):
    """
    显示进度条，格式为: XXXX: XXXX [####----] 33% ETA 01:23 当前任务提示

    参数:
        current (int): 当前进度
        total (int): 总任务数
        description (str): 当前任务的描述
        width (int, optional): 终端总宽度，默认为终端宽度
    """
    try:
        terminal_width = min(100, shutil.get_terminal_size().columns)
    except:
        terminal_width = 80  # 默认宽度

    # 固定布局宽度
    left_width = 10  # 左侧 "XXXX: XXXX" 的宽度
    progress_bar_width = 20  # 进度条宽度
    percent_eta_width = 15  # 百分比和 ETA 的宽度 ("33% ETA 01:23")
    description_width = min(20, terminal_width - left_width - progress_bar_width - percent_eta_width - 10)  # 预留空格

    # 限制描述长度并添加省略号
    if len(description) > description_width:
        description = description[:description_width - 3] + "..."

    # 计算完成百分比
    percent = current / total
    percent_str = f"{percent * 100:3.0f}%"  # 百分比字符串

    # 计算 ETA (预计剩余时间)
    if not hasattr(display_progress_bar, "start_time"):
        display_progress_bar.start_time = time.time()

    elapsed = time.time() - display_progress_bar.start_time
    if current > 0:
        eta_seconds = (elapsed / current) * (total - current)
        eta_min, eta_sec = divmod(int(eta_seconds), 60)
        eta_str = f"ETA {eta_min:02d}:{eta_sec:02d}"
    else:
        eta_str = "ETA --:--"

    # 构建进度条字符串
    completed = int(progress_bar_width * percent)
    progress_bar = "#" * completed + "-" * (progress_bar_width - completed)

    # 构建完整的进度显示
    progress_str = f"{current:4}/{total:<4} [{progress_bar}] {percent_str} {eta_str} {description}"
    if len(progress_str) > terminal_width:
        progress_str = progress_str[:terminal_width - 3] + "..."

    # 清除当前行并显示进度
    sys.stdout.write("\r" + " " * terminal_width)  # 清除整行
    sys.stdout.write("\r" + progress_str)
    sys.stdout.flush()

    # 保存最后显示的行，以便下次清除
    display_progress_bar.last_line = progress_str

    # 如果完成，添加换行
    if current == total:
        sys.stdout.write("\n")
        sys.stdout.flush()
        if hasattr(display_progress_bar, "start_time"):
            delattr(display_progress_bar, "start_time")


#############################################################
# CONFIGURATION AND LOGGING FUNCTIONS
#############################################################

# Functions in this section handle configuration loading and logging.
# These include `load_config`, `trace_debug`, and `log_debug`.

def load_config(config_path):
    """
    从 YAML 文件加载配置。

    参数:
        config_path (str): 配置文件的路径

    返回:
        dict: 配置字典，如果加载失败则返回空字典
    """
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading configuration file {config_path}: {e}")
        return {}

#############################################################
# METADATA VALIDATION AND TASK GENERATION
#############################################################

# Functions in this section handle metadata validation and task generation.
# These include `validate_metadata_mappings`, `read_metadata_lines`,
# `process_metadata_line`, `apply_metadata_actions`, and `generate_metadata_tasks`.

def validate_metadata_mappings(lines, metadata_rules, unmapped_metadata):
    """
    根据规则验证元数据值并跟踪未映射的元数据。

    参数:
        lines (list): Markdown 文件中的行列表
        metadata_rules (dict): 处理元数据的规则
        unmapped_metadata (dict): 用于收集未映射元数据值的字典
    """
    for line in lines:
        key, sep, value = line.partition(": ")
        if not sep:  # Skip lines that are not metadata
            continue

        rule = metadata_rules.get(key)
        if not rule:  # No rule, skip validation
            continue

        actions = rule.get("actions", [])
        for action in actions:
            if action.get("type") == "modify_value":
                value_mapping = action.get("value_mapping", {})
                if value.strip() not in value_mapping and value.strip() not in unmapped_metadata.get(key, set()):
                    unmapped_metadata.setdefault(key, set()).add(value.strip())
    debug(f"验证元数据映射完成: {unmapped_metadata}", LOG_LEVEL_DEBUG, None)

def read_metadata_lines(md_file, metadata_rules, config):
    """
    从 Markdown 文件中提取元数据行（基于新规则）。

    参数:
        md_file (str 或 Path): Markdown 文件的路径
        metadata_rules (dict): 处理元数据的规则
        config (dict): 配置字典，用于日志记录

    返回:
        list: 元数据行的列表
    """
    try:
        with open(md_file, "r") as f:
            content = f.readlines()

        debug(f"Reading metadata lines from {md_file}", LOG_LEVEL_DEBUG, config)

        # Step 1: Read the first 10 lines
        first_10_lines = content[:10]

        # Step 2: Check for a match in metadata_rules
        metadata_start = -1
        for i, line in enumerate(first_10_lines):
            if line.strip().startswith("#"):  # Skip comment lines
                continue
            key, sep, value = line.partition(": ")
            if sep and key.strip() in metadata_rules:
                metadata_start = i
                break

        if metadata_start == -1:
            debug(f"No metadata match found in the first 10 lines of {md_file}", LOG_LEVEL_DEBUG, config)
            return []

        # Step 3: Expand the metadata region
        metadata_lines = []
        # Search backward
        for i in range(metadata_start, -1, -1):
            line = content[i].strip()
            if not line or line == "---":  # Stop at empty or "---" lines
                break
            if ": " in line:  # Include lines with "key: value" format
                metadata_lines.insert(0, line)

        # Search forward
        for i in range(metadata_start + 1, len(content)):
            line = content[i].strip()
            if not line or line == "---":  # Stop at empty or "---" lines
                break
            if ": " in line:  # Include lines with "key: value" format
                metadata_lines.append(line)

        debug(f"从 {md_file} 提取的元数据行: {metadata_lines}", LOG_LEVEL_DEBUG, config)
        return metadata_lines
    except Exception as e:
        debug(f"Error reading metadata from {md_file}: {e}", LOG_LEVEL_ERROR, config)
        return []

def process_metadata_line(line, metadata_rules, config):
    """
    处理单行元数据并根据规则生成任务。

    参数:
        line (str): 单行元数据
        metadata_rules (dict): 处理元数据的规则

    返回:
        list: 转换元数据的任务列表
    """
    key, sep, value = line.partition(": ")
    if not sep:
        return []

    debug(f"开始处理元数据行……: {line}", LOG_LEVEL_DEBUG, config)

    value = value.strip()
    matching_keys = [rule_key for rule_key in metadata_rules if key.startswith(rule_key)]
    if not matching_keys:
        debug(f"⚠️ Warning: No rule defined for metadata key '{key}'.", LOG_LEVEL_ERROR, config)
        return []

    rule = metadata_rules[matching_keys[0]]
    actions = rule.get("actions", [])

    if any(action.get("type") == "delete" for action in actions):
        task = {
            "type": TaskType.TRANSFORM_METADATA.value,
            "key": key,
            "action": {"type": "delete"},
            "file": config.get("current_file")  # 添加文件路径
        }
        debug(f"➕ Added metadata task: {task}", LOG_LEVEL_ACTION, config)
        return [task]

    if any(action.get("type") == "retain" for action in actions) and len(actions) == 1:
        return []

    tasks = apply_metadata_actions(key, value, actions, config)
    
    # Log each metadata task that was generated
    for task in tasks:
        debug(f"➕ Added metadata task: {task}", LOG_LEVEL_ACTION, config)
        
    return tasks

def apply_metadata_actions(key, value, actions, config):
    """
    对键值对应用元数据操作（如 modify_value、append_after、rename）。

    参数:
        key (str): 元数据键
        value (str): 元数据值
        actions (list): 要应用的操作列表

    返回:
        list: 转换任务列表
    """
    tasks = []
    current_key, current_value = key, value
    modified = False

    sorted_actions = sorted(
        [a for a in actions if a.get("type") not in ["retain", "delete"]],
        key=lambda x: {"modify_value": 0, "append_after": 1, "rename": 2}.get(x.get("type"), 999)
    )

    for action in sorted_actions:
        action_type = action.get("type")
        if action_type == "modify_value":
            value_mapping = action.get("value_mapping", {})
            regex_mapping = action.get("regex_mapping", [])
            if current_value in value_mapping:
                current_value = value_mapping[current_value]
                modified = True
            else:
                for regex, replacement in regex_mapping:
                    match = re.search(regex, current_value)
                    if match:
                        # Check if the regex contains capturing groups
                        if match.groups():
                            # Use the regex replacement with capture groups
                            current_value = re.sub(regex, replacement, current_value)
                        else:
                            # No capture groups, use replacement as default
                            current_value = replacement
                        modified = True
                        break
        elif action_type == "append_after":
            current_value += action.get("content", "")
            modified = True
        elif action_type == "rename":
            current_key = action.get("new_name", key)
            modified = True

    if modified:
        tasks.append({
            "type": TaskType.TRANSFORM_METADATA.value,
            "key": key,
            "original_line": f"{key}: {value}",
            "new_line": f"{current_key}: {current_value}",
            "action": {"type": "replace"},
            "file": config.get("current_file")  # Ensure 'file' key is included
        })
    return tasks

def generate_metadata_tasks(md_file, metadata_rules, config):
    """
    解析 Markdown 文件中的元数据并生成转换任务。

    参数:
        md_file (str 或 Path): Markdown 文件的路径
        metadata_rules (dict): 处理元数据的规则
        config (dict): 配置字典

    返回:
        list: 元数据转换任务列表
    """
    tasks = []
    metadata_lines = read_metadata_lines(md_file, metadata_rules, config)  # Pass metadata_rules here
    for line in metadata_lines:
        tasks.extend(process_metadata_line(line, metadata_rules, config))
    return tasks

#############################################################
# DIRECTORY SCANNING AND TASK PLANNING
#############################################################

# Functions in this section handle scanning directories and planning tasks.
# These include `initialize_scan_stats`, `scan_markdown_file`,
# `scan_attachments`, `generate_rename_markdown_task`, and `scan_directory`.

def initialize_scan_stats():
    """
    初始化扫描过程的统计信息和变量。

    返回:
        tuple: 包含统计信息字典、未映射元数据字典和已使用名称集合的元组
    """
    return {
        "markdown_files": 0,
        "attachments": 0,
        "conflicts": 0,
        "metadata_tasks": 0,
        "unmapped_metadata": 0
    }, {}, set()


def scan_markdown_file(file, root, directory, resource_dir, metadata_rules, stats, tasks, config):
    """
    处理单个 Markdown 文件。

    参数:
        file (str): Markdown 文件的名称
        root (str): 文件的根目录
        directory (str): 正在扫描的基目录
        resource_dir (Path): 资源目录的路径
        metadata_rules (dict): 处理元数据的规则
        stats (dict): 用于跟踪统计信息的字典
        tasks (list): 用于收集生成任务的列表
        config (dict): 配置字典
    """
    debug("------------------------------------------------------------", LOG_LEVEL_DEBUG, config)
    debug(f"🔍 Processing Markdown file: {file}", LOG_LEVEL_DEBUG, config)

    original_path = Path(root) / file
    stats["markdown_files"] += 1

    # Step 1: Add metadata mapping tasks
    debug("🛠️ 1.Generating metadata transformation tasks...", LOG_LEVEL_DEBUG, config)  # Changed to DEBUG
    config["current_file"] = str(original_path)  # 设置当前文件路径
    metadata_tasks = generate_metadata_tasks(original_path, metadata_rules, config)
    tasks.extend(metadata_tasks)
    stats["metadata_tasks"] += len(metadata_tasks)

    # Step 2: Process attachments
    debug("📦 2.Processing attachments...", LOG_LEVEL_DEBUG, config)  # Changed to DEBUG
    path_mapping = scan_attachments(original_path, directory, resource_dir, stats, tasks, config)

    # Step 3: Update references in Markdown file
    debug("🔗 3.Updating references in Markdown file...", LOG_LEVEL_DEBUG, config)  # Changed to DEBUG
    if path_mapping:  # Only add the task if path_mapping is not empty
        update_task = {"type": TaskType.UPDATE_ATTACH_REF.value, "file": original_path, "path_mapping": path_mapping}
        debug(f"➕ Added update references task: {update_task}", LOG_LEVEL_ACTION, config)
        tasks.append(update_task)

    # Step 4: Rename Markdown file
    debug("✏️ 4.Renaming Markdown file...", LOG_LEVEL_DEBUG, config)  # Changed to DEBUG
    rename_task = generate_rename_markdown_task(original_path, directory, tasks, config)
    if rename_task:
        debug(f"➕ Added rename task: {rename_task}", LOG_LEVEL_ACTION, config)

    debug(f"✅ 5.Finished processing Markdown file: {file}", LOG_LEVEL_DEBUG, config)  # Changed to DEBUG

def scan_attachments(original_path, directory, resource_dir, stats, tasks, config):
    """
    处理给定 Markdown 文件的附件。

    参数:
        original_path (Path): Markdown 文件的路径
        directory (str): 正在扫描的基目录
        resource_dir (Path): 资源目录的路径
        stats (dict): 用于跟踪统计信息的字典
        tasks (list): 用于收集生成任务的列表
        config (dict): 配置字典

    返回:
        dict: 旧附件路径到新路径的映射
    """
    # Extract UID from the Markdown filename
    uid_match = re.search(r" (\w{32})\.md$", str(original_path))
    attachment_dir = None
    
    if uid_match:
        uid = uid_match.group(1)
        debug(f"📌 Found UID in Markdown filename: {uid}", LOG_LEVEL_DEBUG, config)
        
        # Look for an attachment directory with matching UID in its name
        parent_dir = original_path.parent
        potential_dirs = [d for d in parent_dir.iterdir() if d.is_dir()]
        
        for pot_dir in potential_dirs:
            if uid in pot_dir.name:
                attachment_dir = pot_dir
                debug(f"📂 Found matching attachment directory: {attachment_dir}", LOG_LEVEL_DEBUG, config)
                break
    
    # If no attachment directory with matching UID is found, assume no attachments
    if not attachment_dir:
        debug(f"ℹ️ No attachment directory found for {original_path.name}, skipping attachment processing", LOG_LEVEL_DEBUG, config)
        return {}  # Return empty mapping as there are no attachments

    path_mapping = {}
    if attachment_dir.exists():
        attachment_count = sum(1 for _ in attachment_dir.iterdir())
        debug(f"📄 Found {attachment_count} attachments in {attachment_dir}", LOG_LEVEL_DEBUG, config)
        
        for i, attachment in enumerate(attachment_dir.iterdir(), start=1):
            stats["attachments"] += 1
            if attachment_count == 1:
                # Single attachment: Use Markdown file name
                new_attachment_name = f"{original_path.stem}{attachment.suffix}"
            else:
                # Multiple attachments: Append sequence number
                new_attachment_name = f"{original_path.stem}_{i}{attachment.suffix}"
            new_attachment_path = resource_dir / new_attachment_name
            old_path = quote(str(attachment.relative_to(directory)).replace("\\", "/"))
            new_path = str(new_attachment_path.relative_to(directory)).replace("\\", "/")
            path_mapping[old_path] = new_path
            move_task = {"type": TaskType.MOVE_ATTACHMENT.value, "src": attachment, "dest": new_attachment_path}
            debug(f"➕ Added move attachment task: {move_task}", LOG_LEVEL_ACTION, config)
            tasks.append(move_task)
        
        # 如果转移的附件数量和目录中的文件数量相同，则添加清理任务
        if len(path_mapping) == attachment_count:
            cleanup_task = {
                "type": TaskType.CLEANUP.value,
                "attachment_dir": attachment_dir
            }
            debug(f"➕ Added cleanup task: {cleanup_task}", LOG_LEVEL_ACTION, config)
            tasks.append(cleanup_task)
        else:
            # 如果目录中还有剩余文件，则将目录移动到 trash_output_path
            trash_output_path = config.get("trash_output_path", "Trash")
            trash_dir = Path(directory) / trash_output_path
            trash_dir.mkdir(exist_ok=True)
            move_to_trash_task = {
                "type": TaskType.MOVE_ATTACHMENT.value,
                "src": attachment_dir,
                "dest": trash_dir
            }
            debug(f"➕ Added move to trash task: {move_to_trash_task}", LOG_LEVEL_ACTION, config)
            tasks.append(move_to_trash_task)
    
    return path_mapping

def generate_rename_markdown_task(original_path, directory, tasks, config):
    """
    通过移除 UID 并解决冲突来重命名 Markdown 文件。

    参数:
        original_path (Path): Markdown 文件的路径
        directory (str): 正在扫描的基目录
        tasks (list): 用于收集生成任务的列表
        config (dict): 配置字典

    返回:
        dict: 添加到任务列表中的重命名任务
    """
    base_name = re.sub(r" \w{32}$", "", original_path.stem)  # Remove UID
    new_name = base_name
    counter = 1
    while new_name in [task.get("dest", "").stem for task in tasks if task["type"] == TaskType.RENAME_MD.value]:
        new_name = f"{base_name}_{counter}"
        counter += 1
    new_md_path = Path(directory) / f"{new_name}.md"
    rename_task = {"type": TaskType.RENAME_MD.value, "src": original_path, "dest": new_md_path}
    tasks.append(rename_task)
    return rename_task


def scan_directory(directory, attachment_output_path, metadata_rules, config):
    """
    扫描目录中的 Markdown 文件并生成处理任务。

    参数:
        directory (str): 要扫描的目录路径
        attachment_output_path (str): 资源目录的名称
        metadata_rules (dict): 处理元数据的规则
        config (dict): 配置字典

    返回:
        tuple: 包含任务列表、统计信息字典和未映射元数据字典的元组
    """
    tasks = []
    stats, unmapped_metadata, used_names = initialize_scan_stats()
    resource_dir = Path(directory) / attachment_output_path
    resource_dir.mkdir(exist_ok=True)

    debug(f"📂 Resource directory created at: {resource_dir}", LOG_LEVEL_DEBUG, config)  # Changed to DEBUG

    # 获取所有 Markdown 文件数量用于进度条
    if not config.get("debug", False):
        md_files = []
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".md"):
                    md_files.append(os.path.join(root, file))
        total_files = len(md_files)
        current_file = 0
        
        # 重置进度条计时器
        if hasattr(display_progress_bar, "start_time"):
            delattr(display_progress_bar, "start_time")

    # Scan for Markdown files
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".md"):
                if not config.get("debug", False):
                    current_file += 1
                    display_progress_bar(current_file, total_files, f"扫描: {file}")
                
                debug(f"📄 Found Markdown file: {file}", LOG_LEVEL_DEBUG, config)  # Changed to DEBUG
                scan_markdown_file(file, root, directory, resource_dir, metadata_rules, stats, tasks, config)

    return tasks, stats, unmapped_metadata

#############################################################
# TASK EXECUTION
#############################################################

# Functions in this section handle task execution.
# These include `execute_task` and `execute_tasks`.

def execute_task(task, config, path_mapping):
    """
    根据任务类型执行单个任务。

    参数:
        task (dict): 要执行的任务
        config (dict): 配置字典
        path_mapping (dict): 旧路径到新路径的映射
    """
    try:
        if task["type"] == TaskType.RENAME_MD.value:
            debug(f"✏️ 重命名文件: {task['src']} -> {task['dest']}", LOG_LEVEL_ACTION, config)
            Path(task["src"]).rename(task["dest"])
            path_mapping[str(task["src"])] = str(task["dest"])
        elif task["type"] == TaskType.MOVE_ATTACHMENT.value:
            debug(f"📦 移动附件: {task['src']} -> {task['dest']}", LOG_LEVEL_ACTION, config)
            Path(task["src"]).rename(task["dest"])
        elif task["type"] == TaskType.UPDATE_ATTACH_REF.value:
            debug(f"🔗 更新文件中的引用: {task['file']}", LOG_LEVEL_ACTION, config)
            update_references_in_markdown(task["file"], task["path_mapping"], config.get("metadata_rules", {}), config)
        elif task["type"] == TaskType.TRANSFORM_METADATA.value:
            debug(f"🛠️ 转换文件中的元数据: {task['file']}", LOG_LEVEL_ACTION, config)
            map_metadata(task["file"], config.get("metadata_rules", {}), config)
        elif task["type"] == TaskType.CLEANUP.value:
            debug(f"🗑️ 清理文件: {task['md_file']}", LOG_LEVEL_ACTION, config)
            if task["md_file"].exists():
                task["md_file"].unlink()
            if task["attachment_dir"].exists():
                shutil.rmtree(task["attachment_dir"])
    except Exception as e:
        debug(f"❌ 执行任务 {task['type']} 时出错 - 任务详情: {task}", LOG_LEVEL_ERROR, config)
        debug(f"   错误信息: {e}", LOG_LEVEL_ERROR, config)
        if config.get("stop_on_error", False):
            raise

def execute_tasks(tasks, config):
    """
    按生成顺序执行任务列表。

    参数:
        tasks (list): 要执行的任务列表
        config (dict): 配置字典
    """
    path_mapping = {}
    total_tasks = len(tasks)
    
    # 重置进度条计时器
    if hasattr(display_progress_bar, "start_time"):
        delattr(display_progress_bar, "start_time")
    
    for i, task in enumerate(tasks, start=1):
        task_type = task['type']
        task_desc = ""
        
        if task_type == TaskType.RENAME_MD.value:
            task_desc = f"重命名: {Path(task['src']).name}"
        elif task_type == TaskType.MOVE_ATTACHMENT.value:
            task_desc = f"移动附件: {Path(task['src']).name}"
        elif task_type == TaskType.UPDATE_ATTACH_REF.value:
            task_desc = f"更新引用: {Path(task['file']).name}"
        elif task_type == TaskType.TRANSFORM_METADATA.value:
            task_desc = f"转换元数据"
        
        if not config.get("debug", False):
            display_progress_bar(i, total_tasks, task_desc)
        
        debug(f"⚙️ Executing task {i}/{total_tasks}: {task['type']}", LOG_LEVEL_DEBUG, config)
        execute_task(task, config, path_mapping)    

#############################################################
# METADATA TRANSFORMATION
#############################################################

# Functions in this section handle metadata transformation.
# These include `apply_action`, `transform_metadata`, `update_references_in_markdown`, and `map_metadata`.

def apply_action(key, value, action, config):
    """
    对键值对应用元数据转换操作。

    参数:
        key (str): 元数据键
        value (str): 元数据值
        action (dict): 要应用的操作
        config (dict, optional): 配置字典

    返回:
        tuple: (新键, 新值) 或 (None, None)（如果元数据应被删除）
    """
    debug(f"🔧 Applying action '{action.get('type')}' on key '{key}' with value '{value}'", LOG_LEVEL_DEBUG, config)
    action_type = action.get("type")
    if action_type == "delete":
        debug(f"🗑️ Deleting metadata key: {key}", LOG_LEVEL_ACTION, config)
        return None, None  # Indicate deletion
    elif action_type == "rename":
        new_name = action.get("new_name", key)
        debug(f"✏️ Renaming key '{key}' to '{new_name}'", LOG_LEVEL_ACTION, config)
        return new_name, value
    elif action_type == "modify_value":
        value_mapping = action.get("value_mapping", {})
        regex_mapping = action.get("regex_mapping", [])
        new_value = value.strip()

        # Apply direct value mapping
        if new_value in value_mapping:
            debug(f"🔄 Mapping value '{new_value}' to '{value_mapping[new_value]}'", LOG_LEVEL_ACTION, config)
            new_value = value_mapping[new_value]

        # Apply regex-based transformations
        for regex, replacement in regex_mapping:
            if re.search(regex, new_value):
                debug(f"🔍 Regex '{regex}' matched. Replacing '{new_value}' with '{replacement}'", LOG_LEVEL_ACTION, config)
                new_value = re.sub(regex, replacement, new_value)
                break

        return key, new_value
    elif action_type == "append_after":
        content = action.get("content", "")
        debug(f"➕ Appending '{content}' to value '{value.strip()}'", LOG_LEVEL_ACTION, config)
        return key, f"{value.strip()}{content}"
    else:
        debug(f"⚠️ Unsupported action type '{action_type}' for key '{key}'", LOG_LEVEL_ERROR, config)
        return key, value

def transform_metadata(lines, metadata_rules, config):
    """
    根据规则转换元数据行。

    参数:
        lines (list): 可能包含元数据的行列表
        metadata_rules (dict): 处理元数据的规则
        config (dict, optional): 配置字典

    返回:
        list: 转换后的行
    """
    debug("Starting metadata transformation...", LOG_LEVEL_DEBUG, config)
    transformed_lines = []
    for line in lines:
        if line.strip().startswith('#'):
            continue
        key, sep, value = line.partition(": ")
        if not sep:  # Skip lines that are not metadata
            transformed_lines.append(line)
            continue

        debug(f"🔍 Processing metadata: {key}: {value.strip()}", LOG_LEVEL_DEBUG, config)
        rule = metadata_rules.get(key)
        if not rule:  # No rule, retain the line
            debug(f"⚠️ No rule found for key: {key}", LOG_LEVEL_ERROR, config)
            transformed_lines.append(line)
            continue

        actions = rule.get("actions", [])
        debug(f"🔧 Found {len(actions)} actions for key: {key}", LOG_LEVEL_DEBUG, config)

        current_key, current_value = key, value.strip()
        for i, action in enumerate(actions):
            debug(f"🔧 Applying action {i + 1}: {action.get('type')}", LOG_LEVEL_DEBUG, config)
            current_key, current_value = apply_action(current_key, current_value, action, config)
            if current_key is None:  # If deleted, stop processing further actions
                debug(f"🗑️ Key deleted: {key}", LOG_LEVEL_ACTION, config)
                break

        if current_key is not None:  # If not deleted, add the transformed metadata
            transformed_line = f"{current_key}: {current_value}"
            debug(f"✅ Transformed: {transformed_line}", LOG_LEVEL_ACTION, config)
            transformed_lines.append(transformed_line)

    return transformed_lines

def update_references_in_markdown(file, path_mapping, metadata_rules, config):
    """
    更新 Markdown 文件中的引用并转换元数据。

    参数:
        file (str或Path): Markdown 文件的路径。
        path_mapping (dict): 旧路径到新路径的映射。
        metadata_rules (dict): 处理元数据的规则。
        config (dict, optional): 用于日志记录的配置。
    """
    try:
        with open(file, "r") as f:
            content = f.readlines()

        debug(f"Updating references and metadata in: {file}", LOG_LEVEL_DEBUG, config)
        debug(f"Path mapping: {path_mapping}", LOG_LEVEL_DEBUG, config)

        # Process metadata transformation
        metadata_end_index = 0
        for i, line in enumerate(content):
            if line.strip() == "":  # Assume metadata ends at the first blank line
                metadata_end_index = i
                break

        metadata_lines = content[:metadata_end_index]
        transformed_metadata = transform_metadata(metadata_lines, metadata_rules, config)
        content = transformed_metadata + content[metadata_end_index:]

        # Update references
        updated_content = []
        for i, line in enumerate(content, start=1):
            original_line = line
            for old_path, new_path in path_mapping.items():
                if old_path in line:
                    encoded_new_path = quote(new_path)
                    line = line.replace(old_path, encoded_new_path)
                    debug(f"Line {i}:\n   Original: {original_line.strip()}\n   Updated:  {line.strip()}", LOG_LEVEL_DEBUG, config)
                    debug(f"Updated reference in {file} line {i}: {old_path} -> {encoded_new_path}", LOG_LEVEL_ACTION, config)
            updated_content.append(line)

        with open(file, "w") as f:
            f.writelines(updated_content)

        debug(f"更新文件 {file} 中的引用完成", LOG_LEVEL_ACTION, config)
    except Exception as e:
        debug(f"❌ Error updating references in {file}: {e}", LOG_LEVEL_ERROR, config)

def map_metadata(file, metadata_rules, config):
    """
    映射并转换 Markdown 文件中的元数据。

    参数:
        file (str 或 Path): Markdown 文件的路径
        metadata_rules (dict): 处理元数据的规则
        config (dict, optional): 配置字典
    """
    try:
        rule_summary = {key: {"rules_found": len(value.get("actions", [])), 
                    "types": [a.get("type") for a in value.get("actions", [])]} 
                for key, value in metadata_rules.items()}
        debug(f"📋 Metadata rules summary: {rule_summary}", LOG_LEVEL_DEBUG, config)
        with open(file, "r") as f:
            content = f.readlines()

        metadata_end_index = 0
        for i, line in enumerate(content):
            if line.strip() == "":  # Assume metadata ends at the first blank line
                metadata_end_index = i
                break

        metadata_lines = content[:metadata_end_index]
        transformed_metadata = transform_metadata(metadata_lines, metadata_rules, config)

        debug(f"Metadata changes for {file}:", LOG_LEVEL_DEBUG, config)
        for original, transformed in zip(metadata_lines, transformed_metadata):
            if original.strip() != transformed.strip():
                debug(f"   Original: {original.strip()}\n   Transformed: {transformed.strip()}", LOG_LEVEL_DEBUG, config)
                debug(f"Transformed metadata in {file}: {original.strip()} -> {transformed.strip()}", LOG_LEVEL_ACTION, config)

        content = transformed_metadata + content[metadata_end_index:]

        with open(file, "w") as f:
            f.writelines(content)

        debug(f"映射文件 {file} 的元数据完成", LOG_LEVEL_ACTION, config)
    except Exception as e:
        debug(f"❌ Error mapping metadata in {file}: {e}", LOG_LEVEL_ERROR, config)

#############################################################
# MAIN FUNCTION
#############################################################

# Functions in this section handle the main script execution.
# These include `print_introduction`, `parse_arguments`, `load_and_configure`,
# `print_statistics`, `confirm_execution`, `print_final_statistics`, and `main`.

def print_introduction():
    """
    打印脚本的简要介绍。
    """
    intro = """
💼 Obsidian Import Tool 📚
--------------------------
A tool to process Notion exports for use in Obsidian.

This tool helps you:
- Clean up filenames by removing UIDs
- Consolidate all attachments into a single resource directory
- Update markdown references to point to the new paths
- Transform metadata based on custom rules

Usage examples:
  python3 obsidian_import.py /path/to/notion/export  # Process an export directory
  python3 obsidian_import.py --help                  # Show all available options

Get started by running with a directory path.
"""
    print(intro)

def parse_arguments():
    """
    解析命令行参数。
    """
    parser = argparse.ArgumentParser(
        description="Transform Notion exports for use in Obsidian - consolidates resources and cleans up metadata.",
        epilog="For detailed documentation, refer to the script comments."
    )
    parser.add_argument("directory", help="The directory to process", nargs="?")
    parser.add_argument("--config", help="Path to the configuration file", default="obsidian_import.yaml")
    parser.add_argument("--log", nargs="?", const=LOG_LEVEL_ACTION, choices=LOG_LEVELS.keys(), type=str.lower,
                        help="Enable logging to a file with an optional log level (default: ACT if no level is provided)")
    parser.add_argument("--verbose", nargs="?", const=LOG_LEVEL_ACTION, choices=LOG_LEVELS.keys(), type=str.lower,
                        help="Enable verbose output with an optional stdout level (default: ACT if no level is provided)")
    parser.add_argument("--reset-log", action="store_true", help="Clear the log file before starting")
    return parser

def load_and_configure(args):
    """
    从文件加载配置并应用命令行参数覆盖。

    参数:
        args (argparse.Namespace): 解析的命令行参数

    返回:
        dict: 应用覆盖后的配置字典
    """
    config = load_config(args.config)

    # Apply command-line overrides
    config["log_file"] = "obsidian_import.log" if args.log else None
    config["log_level"] = args.log if args.log else LOG_LEVEL_ACTION
    config["stdout_level"] = args.verbose if args.verbose else LOG_LEVEL_FLOW
    config["reset_log"] = args.reset_log

    return config

def print_statistics(stats, unmapped_metadata, tasks):
    """
    打印总结任务的统计信息。

    参数:
        stats (dict): 包含扫描统计信息的字典
        unmapped_metadata (dict): 未映射元数据值的字典
        tasks (list): 扫描期间生成的任务列表
    """
    # 如果有进度条，确保在打印统计信息前完成进度条
    if hasattr(display_progress_bar, "last_line"):
        sys.stdout.write("\n")
        sys.stdout.flush()

    print("\n📊 扫描统计信息:")
    print("-------------------")
    print(f"处理的 Markdown 文件数量: {stats.get('markdown_files', 0)}")
    print(f"处理的附件数量: {stats.get('attachments', 0)}")
    print(f"元数据转换任务数量: {stats.get('metadata_tasks', 0)}")
    print(f"未映射的元数据条目: {stats.get('unmapped_metadata', 0)}")
    print(f"生成的总任务数量: {len(tasks)}")

    if unmapped_metadata:
        print("\n⚠️ 未映射的元数据:")
        for key, values in unmapped_metadata.items():
            print(f"  - {key}: {', '.join(values)}")

    print("\n📋 任务摘要:")
    task_counts = {}
    for task in tasks:
        task_type = task['type']
        if task_type not in task_counts:
            task_counts[task_type] = 0
        task_counts[task_type] += 1
    
    for task_type, count in task_counts.items():
        print(f"  • {task_type}: {count} 个任务")

def confirm_execution():
    """
    在执行任务列表之前提示用户确认。

    返回:
        bool: 如果用户确认则为 True，否则为 False
    """
    response = input("Do you want to proceed with the tasks? (yes/no): ").strip().lower()
    return response in ["yes", "y"]

def print_final_statistics(tasks, execution_time, config):
    """
    在执行任务后打印最终统计信息。

    参数:
        tasks (list): 已执行的任务列表
        execution_time (float): 总执行时间（秒）
        config (dict): 配置字典
    """
    print("\n✅ Task Execution Complete")
    print("--------------------------")
    print(f"Total tasks executed: {len(tasks)}")
    print(f"Execution time: {execution_time:.2f} seconds")

    if config.get("log_debug", False):
        debug(f"Task execution completed in {execution_time:.2f} seconds", LOG_LEVEL_ACTION, config)

def main():
    """
    主函数，用于协调 Obsidian 导入过程。

    步骤:
    1. 解析命令行参数
    2. 加载配置并应用覆盖
    3. 扫描目录并生成任务
    4. 打印统计信息并提示确认
    5. 如果确认，执行任务
    6. 打印最终统计信息和执行时间
    """
    parser = parse_arguments()
    if len(sys.argv) == 1:
        print_introduction()
        parser.print_help()
        return

    args = parser.parse_args()

    if not args.directory:
        parser.error("the following arguments are required: directory")

    try:
        config = load_and_configure(args)
        
        # Initialize the log file if requested
        initialize_log_file(config)
        
        debug("🚀 Starting Obsidian Import Tool...", LOG_LEVEL_FLOW, config)

        directory = args.directory
        attachment_output_path = config.get("attachment_output_path", "Resource")
        metadata_rules = config.get("metadata_rules", {})

        if config.get("log_file"):
            debug(f"Starting obsidian_import.py on {directory}", LOG_LEVEL_ACTION, config)

        # Step 1: Scan the directory
        debug("🚀 Starting directory scan...", LOG_LEVEL_FLOW, config)
        tasks, stats, unmapped_metadata = scan_directory(directory, attachment_output_path, metadata_rules, config)
        debug("✅ Directory scan completed.", LOG_LEVEL_FLOW, config)  # Changed to DEBUG

        # Step 2: Display statistics
        print_statistics(stats, unmapped_metadata, tasks)

        # Step 3: Prompt for confirmation
        if not confirm_execution():
            debug("Operation canceled by the user.", LOG_LEVEL_ACTION, config)
            return

        # Step 4: Execute tasks
        debug("🚀 Starting task execution...", LOG_LEVEL_FLOW, config)
        start_time = time.time()
        execute_tasks(tasks, config)
        end_time = time.time()
        debug("✅ Task execution completed.", LOG_LEVEL_FLOW, config)

        # Step 5: Print final statistics
        print_final_statistics(tasks, end_time - start_time, config)
        debug("✅ Obsidian Import Tool completed.", LOG_LEVEL_FLOW, config)
    finally:
        close_log_file(config)

if __name__ == "__main__":
    main()
