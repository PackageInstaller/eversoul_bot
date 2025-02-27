import ast
import os
import re
import json
import yaml
import httpx
import asyncio
import subprocess
import time as time_module
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from pathlib import Path
from typing import Tuple, Any, Optional
from io import BytesIO
from nonebot.plugin import PluginMetadata
from nonebot import require, on_command, on_regex, get_bot
from datetime import datetime
from nonebot.exception import FinishedException
from nonebot.permission import SUPERUSER
from PIL import Image, ImageDraw
from difflib import get_close_matches
from zhenxun.services.log import logger
from nonebot.params import CommandArg, RegexGroup
from nonebot.adapters.onebot.v11 import (
    Bot,
    Event,
    GROUP_ADMIN,
    GROUP_OWNER,
    Message,
    MessageSegment,
    GroupMessageEvent
)
require("nonebot_plugin_htmlrender")
from zhenxun.utils.enum import PluginType
from zhenxun.configs.utils import PluginExtraData
from zhenxun.utils.enum import BlockType, PluginType
from zhenxun.configs.utils import BaseBlock, PluginExtraData
from nonebot_plugin_htmlrender import html_to_pic

__plugin_meta__ = PluginMetadata(
    name="Eversoul工具合集",
    description="Eversoul相关信息查询",
    usage="""
    使用 es 命令列表 指令获取相关信息
    """.strip(),
    extra=PluginExtraData(
        author="少姜",
        version="1.0",
        plugin_type=PluginType.NORMAL,
        limits=[BaseBlock(check_type=BlockType.GROUP)],
        menu_type="功能"
    ).dict(),
)

es_help = on_command("es命令列表", aliases={"es帮助", "es指令列表"}, priority=5, block=True)
es_hero_info = on_command("es角色信息", priority=5, block=True)
es_hero_list = on_command("es角色列表", priority=5, block=True)
es_stage_info = on_command("es主线信息", priority=5, block=True)
es_month = on_regex(r"^es(\d{1,2})月事件$", priority=5, block=True)
es_stats = on_regex(r"^es(身高|体重)排行$", priority=5, block=True)
es_level_cost = on_regex(r"^es升级消耗(\d+)$", priority=5, block=True)
es_ark_info = on_regex(r"^es方舟等级信息(\d+)$", priority=5, block=True)
es_gate = on_regex(r"es(自由|人类|野兽|妖精|不死)传送门信息(\d+)", priority=5, block=True)
es_cash_info = on_command("es突发礼包信息", priority=5, block=True)
es_tier_info = on_command("es礼品信息", priority=5, block=True)
es_potential_info = on_command("es潜能信息", priority=5, block=True)
es_avatar_frame = on_command("es头像框", priority=5, block=True)
es_check_update = on_command("es检查更新", priority=5, permission=(SUPERUSER | GROUP_ADMIN | GROUP_OWNER), block=True)
es_switch_source = on_command("es数据源切换", priority=5, permission=(SUPERUSER | GROUP_ADMIN | GROUP_OWNER), block=True)

# 传送门类型
GATE_TYPES = {
    "自由": 4,
    "人类": 5,
    "野兽": 6,
    "妖精": 7,
    "不死": 8
}

stat_names = {
    "attack_rate": "攻击力",
    "attack": "攻击力",
    "defence_rate": "防御力",
    "defence": "防御力",
    "max_hp_rate": "体力",
    "max_hp": "体力",
    "hp_rate": "体力",
    "hp": "体力",
    "critical_rate": "暴击率",
    "critical_power": "暴击威力",
    "hit": "命中",
    "dodge": "闪避",
    "physical_resist": "物理抵抗",
    "magic_resist": "魔法抵抗",
    "life_leech": "噬血",
    "attack_speed": "攻击速度"
}

# 属性限制映射
stat_mapping = {
    "智力": 110044,
    "敏捷": 110043,
    "力量": 110042,
    "共用": 110041
}

# 组合效果映射
effect_mapping = {
    "攻击力": 14101,
    "防御力": 14102,
    "体力": 14103,
    "暴击率": 14104,
    "暴击威力": 14105,
    "回避": 14107,
    "加速": 14111
}

# 添加数据源配置文件路径
DATA_SOURCE_CONFIG = Path(__file__).parent / "data_source_config.yaml"

# 默认配置
DEFAULT_CONFIG = {
    "type": "live",
    "json_path": str(Path("/home/rikka/Eversoul/live_jsons")),
    "hero_alias_file": str(Path(__file__).parent / "live_hero_aliases.yaml")
}

# 全局变量来存储当前数据源配置
current_data_source = {
    "type": "live",  # 默认使用live
    "json_path": Path("/home/rikka/Eversoul/live_jsons"),
    "hero_alias_file": Path(__file__).parent / "live_hero_aliases.yaml"
}

FONT_PATH = "/home/rikka/zhenxun_bot/zhenxun/plugins/zhenxun_plugin_draw_painting/font/Sarasa-Regular.ttc"
custom_font = FontProperties(fname=FONT_PATH)

# 加载别名配置文件
def load_aliases():
    """加载角色别名配置"""
    hero_alias_file = current_data_source["hero_alias_file"]
    if not hero_alias_file.exists():
        return {}
    
    try:
        with open(hero_alias_file, "r", encoding="utf-8") as f:
            aliases_data = yaml.safe_load(f)
            if not aliases_data or "names" not in aliases_data:
                return {}
    except Exception as e:
        print(f"加载别名配置文件出错: {e}")
        return {}
    
    # 创建别名到hero_id的映射
    alias_map = {}
    for hero in aliases_data["names"]:
        if isinstance(hero, dict) and "hero_id" in hero:
            # 添加所有语言版本的名称
            name_fields = [
                "zh_tw_name",
                "zh_cn_name",
                "kr_name",
                "en_name"
            ]
            
            # 添加所有非空的名称作为可能的匹配
            for field in name_fields:
                if hero.get(field):  # 只添加非空的名称
                    alias_map[hero[field]] = hero["hero_id"]
                    # 为英文名称添加小写版本
                    if field == "en_name":
                        alias_map[hero[field].lower()] = hero["hero_id"]
            
            # 添加所有别名
            for alias in hero.get("aliases", []):
                alias_map[alias] = hero["hero_id"]
                # 如果别名看起来是英文(只包含ASCII字符),也添加小写版本
                if alias.isascii():
                    alias_map[alias.lower()] = hero["hero_id"]
    
    return alias_map

# 加载所需的JSON文件
def load_json_data():
    json_files = {
        "hero": "Hero.json", # 角色
        "hero_option": "HeroOption.json", # 角色潜能
        "string_char": "StringCharacter.json", # 角色文本
        "string_system": "StringSystem.json", # 系统文本
        "skill": "Skill.json", # 技能
        "string_skill": "StringSkill.json", # 技能文本
        "skill_code": "SkillCode.json", # 技能代码
        "skill_buff": "SkillBuff.json", # 技能效果
        "skill_icon": "SkillIcon.json", # 技能图标
        "signature": "Signature.json", # 遗物
        "hero_desc": "HeroDesc.json", # 角色描述
        "signature_level": "SignatureLevel.json", # 遗物等级
        "story_info": "StoryInfo.json", # 故事信息
        "talk": "Talk.json", # 对话
        "string_talk": "StringTalk.json", # 对话文本
        "item_costume": "ItemCostume.json", # 物品信息
        "item": "Item.json", # 物品
        "item_stat": "ItemStat.json", # 物品属性
        "string_item": "StringItem.json", # 物品文本
        "illust": "Illust.json", # 插画
        "item_drop_group": "ItemDropGroup.json", # 掉落组
        "item_set_effect": "ItemSetEffect.json", # 套装效果
        "stage": "Stage.json", # 关卡
        "stage_battle": "StageBattle.json", # 关卡战斗
        "formation": "Formation.json", # 队伍
        "message_mail": "MessageMail.json", # 邮件
        "level": "Level.json", # 等级
        "ark_enhance": "ArkEnhance.json", # 方舟强化
        "ark_overclock": "ArkOverClock.json", # 超频
        "promotion_movie": "PromotionMovie.json", # 宣传片
        "localization_schedule": "LocalizationSchedule.json", # 活动日历
        "event_calender": "EventCalender.json", # 活动日历
        "string_ui": "StringUI.json", # UI文本
        "eden_alliance": "EdenAlliance.json", # 联合作战
        "stage_equip": "StageEquip.json", # 关卡装备
        "string_stage": "StringStage.json", # 关卡文本
        "cash_shop_item": "CashShopItem.json", # 商店物品
        "string_cashshop": "StringCashshop.json", # 商店文本
        "barrier": "Barrier.json", # 传送门相关信息
        "trip_hero": "TripHero.json", # 角色关键字
        "trip_keyword": "TripKeyword.json", # 角色关键字
        "key_values": "KeyValues.json", # 关键字
        "town_location": "TownLocation.json", # 地点
        "town_object": "TownObjet.json", # 专属领地物品
        "string_town": "StringTown.json", # 地点文本
        "town_lost_item": "TownLostItem.json", # 遗失物品
        "tower": "Tower.json", # 起源塔
        "contents_buff": "ContentsBuff.json", # buff数值内容
        "world_raid_partner_buff": "WorldRaidPartnerBuff.json", # 支援伙伴buff
        "arbeit_choice": "ArbeitChoice.json", # 专属物品任务选择
        "arbeit_list": "ArbeitList.json"   # 专属物品任务列表
    }
    
    data = {}
    for key, filename in json_files.items():
        with open(current_data_source["json_path"] / filename, "r", encoding="utf-8") as f:
            data[key] = json.load(f)
    return data


async def generate_ark_level_chart(data: dict) -> MessageSegment:
    """生成主方舟等级与超频等级关系图"""
    try:
        # 收集数据点
        levels = []
        overclock_levels = []
        
        for ark in data["ark_enhance"]["json"]:
            if ark.get("core_type02") == 110051:  # 主方舟
                level = ark.get("core_level")
                overclock = ark.get("overclock_max_level")
                if level is not None and overclock is not None:
                    levels.append(level)
                    overclock_levels.append(overclock)
        
        # 创建图表
        plt.figure(figsize=(10, 6))
        plt.plot(levels, overclock_levels, 'b-', marker='o', markersize=3)
        
        # 使用自定义字体设置标题和标签
        plt.title('主方舟等级与最大超频等级关系图', fontproperties=custom_font)
        plt.xlabel('主方舟等级', fontproperties=custom_font)
        plt.ylabel('最大超频等级', fontproperties=custom_font)
        
        # 设置网格
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 设置x轴刻度
        plt.xticks(range(0, max(levels)+1, 50))
        
        # 添加关键点标注
        plt.annotate(f'最大值: ({max(levels)}, {max(overclock_levels)})',
                    xy=(max(levels), max(overclock_levels)),
                    xytext=(10, 10),
                    textcoords='offset points',
                    fontproperties=custom_font)
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 获取bytes数据
        buffer.seek(0)
        image_bytes = buffer.getvalue()
        
        # 返回MessageSegment对象
        return MessageSegment.image(image_bytes)
        
    except Exception as e:
        logger.error(f"生成统计图时发生错误: {str(e)}")
        return MessageSegment.text("生成统计图失败")


def format_number(num):
    '''
    递归实现，精确为最大单位值 + 小数点后一位
    处理科学计数法表示的数值
    '''
    def strofsize(num, level):
        if level >= 29:
            return num, level
        elif num >= 10000:
            num /= 10000
            level += 1
            return strofsize(num, level)
        else:
            return num, level
        
    units = ['', '万', '亿', '兆', '京', '垓', '秭', '穰', '沟', '涧', '正', '载', '极', 
             '恒河沙', '阿僧祗', '那由他', '不思议', '无量大', '万无量大', '亿无量大', 
             '兆无量大', '京无量大', '垓无量大', '秭无量大', '穰无量大', '沟无量大', 
             '涧无量大', '正无量大', '载无量大', '极无量大']
    # 处理科学计数法
    if "e" in str(num):
        num = float(f"{num:.1f}")
    num, level = strofsize(num, 0)
    if level >= len(units):
        level = len(units) - 1
    return f"{round(num, 1)}{units[level]}"


def clean_color_tags(text):
    """清理颜色标签"""
    # 处理 <color=#XXXXXX> 格式
    text = re.sub(r'<color=#[A-Fa-f0-9]+>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</color>', '', text, flags=re.IGNORECASE)
    
    # 处理 <COLOR=#XXXXXX> 格式
    text = re.sub(r'<COLOR=#[A-Fa-f0-9]+>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</COLOR>', '', text, flags=re.IGNORECASE)
    
    # 处理可能存在的空格
    text = re.sub(r'<color\s*=#[A-Fa-f0-9]+\s*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</color\s*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<COLOR\s*=#[A-Fa-f0-9]+\s*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</COLOR\s*>', '', text, flags=re.IGNORECASE)
    
    # 处理 <color="#XXXXXX"> 格式（带引号的情况）
    text = re.sub(r'<color="[#A-Fa-f0-9]+"\s*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<COLOR="[#A-Fa-f0-9]+"\s*>', '', text, flags=re.IGNORECASE)
    
    return text


def get_keyword_grade(data: dict, grade_sno: int) -> str:
    """获取关键字稀有度"""
    return next((s.get("zh_tw", "未知") for s in data["string_system"]["json"] 
                if s["no"] == grade_sno), "未知")

def get_keyword_name(data: dict, string_sno: int) -> str:
    """获取关键字名称"""
    return next((s.get("zh_tw", "未知") for s in data["string_ui"]["json"] 
                if s["no"] == string_sno), "未知")

def get_keyword_source(data: dict, source_sno: int, details: int, hero_no: int = None, keyword_type: int = None) -> str:
    """获取关键字解锁条件"""
    
    source = next((s.get("zh_tw", "") for s in data["string_ui"]["json"] 
                  if s["no"] == source_sno), "")
    
    if not source:
        return ""
        
    # 检查是否是遗失物品
    if hero_no and keyword_type:
        lost_item_info = get_lost_item_info(data, hero_no, keyword_type, details)
        if lost_item_info:
            return lost_item_info
        
    if 101 <= details <= 110:
        logger.debug(f"处理地点解锁: details={details}")
        location = next((loc for loc in data["town_location"]["json"] 
                       if loc["no"] == details), None)
        if location:
            location_name = next((s.get("zh_tw", "未知") for s in data["string_town"]["json"] 
                                if s["no"] == location.get("location_name_sno")), "未知")
            return f"在{location_name}解锁"
    elif details == 1:
        logger.debug("处理好感故事篇章")
        try:
            return source.format(1)
        except Exception as e:
            logger.error(f"格式化好感故事篇章失败: {e}, source={source}")
            return f"完成好感故事篇章1"
    elif source_sno == 619006:  # 打工熟练度
        try:
            return source.format(details)
        except Exception as e:
            logger.error(f"格式化打工熟练度失败: {e}, source={source}")
            return f"打工熟练度达Lv.{details}时可获得"
    elif "好感達Lv.{0}" in source or "好感达等级{0}" in source:  # 好感等级
        try:
            return source.format(details)
        except Exception as e:
            logger.error(f"格式化好感等级失败: {e}, source={source}")
            return f"好感达Lv.{details}时可获得"
    else:
        logger.debug(f"处理故事解锁: details={details}")
        story = next((s for s in data["story_info"]["json"] 
                     if s["no"] == details), None)
        if story:
            act = story.get('act', '?')
            episode = story.get('episode', '?')
            logger.debug(f"获取到的章节信息: {act}-{episode}")
            try:
                # 分别处理章和节
                if "{0}{1}" in source:
                    result = source.format(f"第{act}章", episode)
                else:
                    result = source.format(f"{act}-{episode}")
                logger.debug(f"格式化结果: {result}")
                return result
            except Exception as e:
                logger.error(f"格式化故事章节失败: {e}, source={source}, act={act}, episode={episode}")
                return f"完成主线故事第{act}章 {episode}话时可获得"
    
    logger.debug(f"返回原始source: {source}")
    return source

def get_keyword_location(data: dict, keyword_get_details: int) -> str:
    """获取关键字对应的地点"""
    logger.debug(f"尝试获取地点信息: keyword_get_details={keyword_get_details}")
    
    # 如果没有keyword_get_details或为0，返回"通用"
    if not keyword_get_details:
        return "通用"
    
    # 在TownLocation.json中查找对应地点
    location = next((loc for loc in data["town_location"]["json"] 
                    if loc["no"] == keyword_get_details), None)
    logger.debug(f"找到的location: {location}")
    
    if not location:
        return "通用"
    
    # 获取地点名称
    location_name = next((s.get("zh_tw", "") for s in data["string_town"]["json"] 
                         if s["no"] == location.get("location_name_sno")), "")
    logger.debug(f"获取到的地点名称: {location_name}")
    return location_name or "通用"  # 如果获取不到地点名称，也返回"通用"

def get_lost_item_info(data: dict, hero_no: int, keyword_type: int, keyword_get_details: int) -> str:
    """获取遗失物品信息"""
    try:
        logger.debug(f"处理遗失物品: hero_no={hero_no}, keyword_type={keyword_type}, details={keyword_get_details}")
        
        # 在TownLostItem.json中查找对应条目
        lost_item = next((item for item in data["town_lost_item"]["json"] 
                         if item.get("hero_no") == hero_no and 
                         item.get("keyword_type") == keyword_type), None)
        
        if not lost_item:
            return ""
            
        quest_type = lost_item.get("quest_type")
        logger.debug(f"遗失物品类型: {quest_type}")
        
        if quest_type == 3:  # 特定场景遗失
            # 获取地点信息
            if group_trip := lost_item.get("group_trip"):
                # 在Talk.json中查找对应对话
                talks = [t for t in data["talk"]["json"] if t.get("group_no") == group_trip]
                # 找到最后一个带choice的对话
                choice_talk = next((t for t in reversed(talks) if t.get("ui_type") == "choice"), None)
                if choice_talk and choice_talk.get("no"):  # 确保choice_talk存在且有no字段
                    location = next((s.get("zh_tw", "") for s in data["string_talk"]["json"] 
                                   if s.get("no") == choice_talk.get("no")), "")
                    if location:
                        return f"需要{location}"
        else:  # 领地遗失或击杀魔物
            if group_end := lost_item.get("group_end"):
                talks = [t for t in data["talk"]["json"] if t.get("group_no") == group_end]
                choice_talk = next((t for t in reversed(talks) if t.get("ui_type") == "choice"), None)
                if choice_talk and choice_talk.get("no"):  # 确保choice_talk存在且有no字段
                    action = next((s.get("zh_tw", "") for s in data["string_talk"]["json"] 
                                 if s.get("no") == choice_talk.get("no")), "")
                    if quest_type == 4 and keyword_get_details == 1:
                        return f"需要击杀魔物"
                    elif action:
                        return f"需要{action}"
        
        return ""
        
    except Exception as e:
        logger.error(f"处理遗失物品信息时发生错误: {e}, hero_no={hero_no}, keyword_type={keyword_type}, details={keyword_get_details}")
        return ""

def get_keyword_points(data: dict, keyword_type: str) -> list:
    """获取关键字好感度点数"""
    key_name = {
        "normal": "TRIP_KEYWORD_GRADE_POINT",
        "bad": "TRIP_KEYWORD_GRADE_POINT_BAD",
        "good": "TRIP_KEYWORD_GRADE_POINT_GOOD"
    }[keyword_type]
    
    points = next((kv.get("values_data") for kv in data["key_values"]["json"] 
                  if kv.get("key_name") == key_name), None)
    if points:
        try:
            return ast.literal_eval(points)
        except:
            pass
    return [20, 40, 60]  # 默认值


def get_character_portrait(data, hero_id, hero_name_en):
    """获取角色头像
    
    Args:
        data: JSON数据字典
        hero_id: 角色ID
        hero_name_en: 角色英文名称
    Returns:
        Path: 头像图片路径或None
    """
    # 头像路径
    portrait_path = Path(__file__).parent / "hero" / f"{hero_name_en}_512.png"
    if portrait_path.exists():
        return portrait_path
    
    # 如果直接用英文名找不到，尝试从item_costume获取portrait_path
    for costume in data["item_costume"]["json"]:
        if costume.get("hero_no") == hero_id:
            portrait_path = costume.get("portrait_path", "")
            if portrait_path:
                # 构建头像路径
                portrait_file = Path(__file__).parent / "hero" / f"{portrait_path}_512.png"
                if portrait_file.exists():
                    return portrait_file
                break
    
    return None


def get_character_illustration(data, hero_id, hero_name_tw, hero_name_cn):
    """获取角色立绘
    
    Args:
        data: JSON数据字典
        hero_id: 角色ID 
        hero_name_tw: 角色繁体名称
        hero_name_cn: 角色简体名称
    Returns:
        list: [(图片路径, 显示名称_tw, 显示名称_cn, 解锁条件_tw)] 的列表
    """
    image_path = Path(__file__).parent / "hero"
    if not image_path.exists():
        return []
    
    # 获取所有该角色的立绘信息
    costume_info = {}
    for costume in data["item_costume"]["json"]:
        if costume.get("hero_no") == hero_id:
            portrait_path = costume.get("portrait_path", "")
            name_sno = costume.get("name_sno")
            type_sno = costume.get("type_sno")  # 获取时装的type_sno
            if portrait_path and name_sno and type_sno:
                # 从StringItem.json获取立绘名称
                for string in data["string_item"]["json"]:
                    if string["no"] == name_sno:
                        costume_name_tw = string.get("zh_tw", "")
                        costume_name_cn = string.get("zh_cn", "") or string.get("zh_tw", "")
                        if costume_name_tw and costume_name_cn:
                            # 从StringUI.json获取解锁条件
                            condition_tw = ""
                            for ui_string in data["string_ui"]["json"]:
                                if ui_string["no"] == type_sno:
                                    condition_tw = ui_string.get("zh_tw", "")
                                    break
                            costume_info[portrait_path] = (costume_name_tw, costume_name_cn, condition_tw)
                        break
    
    # 查找匹配的图片
    images = []
    for file in image_path.glob('*_2048.*'):
        base_name = file.stem[:-5]  # 移除 _2048 后缀
        if base_name in costume_info:
            # 构建 "角色名_立绘名" 的格式
            costume_name_tw, costume_name_cn, condition_tw = costume_info[base_name]
            display_name_tw = f"{hero_name_tw}_{costume_name_tw}"
            display_name_cn = f"{hero_name_cn}_{costume_name_cn}"
            images.append((file, display_name_tw, display_name_cn, condition_tw))
    
    return sorted(images)  # 排序以保持顺序一致


def get_schedule_events(data, target_month, current_year, schedule_prefix, event_type):
    """获取日程事件信息
    
    Args:
        data: JSON数据字典
        target_month: 目标月份
        current_year: 当前年份
        schedule_prefix: 日程key前缀(如"Calender_SingleRaid_")
        event_type: 事件类型显示名称(如"恶灵讨伐")
    
    Returns:
        list: 事件信息列表
    """
    events = []
    now = datetime.now()
    
    for schedule in data["localization_schedule"]["json"]:
        # 对于主要活动，使用完全匹配而不是startswith
        if schedule_prefix.endswith("_Main"):
            if schedule.get("schedule_key", "") != schedule_prefix:
                continue
        else:
            if not schedule.get("schedule_key", "").startswith(schedule_prefix):
                continue
            
        start_date = schedule.get("start_date")
        end_date = schedule.get("end_date")
        
        if not (start_date and end_date):
            continue
            
        start_date = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
        end_date = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
        
        is_in_month = (
            (start_date.year == current_year and start_date.month == target_month) or
            (end_date.year == current_year and end_date.month == target_month)
        ) and end_date >= now
        
        if not is_in_month:
            continue
            
        schedule_key = schedule["schedule_key"]
        event_name_tw = ""
        
        # 从EventCalender中获取name_sno
        for event in data["event_calender"]["json"]:
            if event.get("schedule_key") == schedule_key:
                name_sno = event.get("name_sno")
                if name_sno:
                    # 从StringUI中获取名称
                    for string in data["string_ui"]["json"]:
                        if string["no"] == name_sno:
                            event_name_tw = string.get("zh_tw", "").replace('\\r\\n', ' ').replace('\r\n', ' ').replace('\n', ' ')
                            break
                break
        
        if event_name_tw:
            event_info = []
            event_info.append(f"【{event_type}】")
            event_info.append(f"名称：{event_name_tw}")
            event_info.append(f"持续时间：{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
            # 返回带开始时间的元组
            events.append((start_date, "\n".join(event_info)))
    
    return events


def get_mail_events(data, target_month, current_year):
    """获取邮箱事件信息"""
    mail_events = []
    now = datetime.now()
    
    for mail in data["message_mail"]["json"]:
        start_date = mail.get("start_date")
        end_date = mail.get("end_date")
        
        if not (start_date and end_date):
            continue
            
        # 将日期字符串转换为datetime对象
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
        
        # 检查事件是否在目标月份内
        is_in_month = (
            (start_date.year == current_year and start_date.month == target_month) or
            (end_date.year == current_year and end_date.month == target_month)
        ) and end_date >= now
        
        if not is_in_month:
            continue
            
        # 获取发送者名称
        sender_name_tw = "未知"
        if sender_sno := mail.get("sender_sno"):
            sender_name_tw, sender_name_cn, sender_name_kr, sender_name_en = get_hero_name_by_id(data, sender_sno)
        
        # 获取标题和描述
        title_tw, title_cn, title_kr, title_en = get_string_char(data, mail.get("title_sno", 0)) or "无标题"
        desc_tw, desc_cn, desc_kr, desc_en = get_string_char(data, mail.get("desc_sno", 0)) or "无描述"
        
        # 处理奖励信息
        rewards = []
        for i in range(1, 5):
            reward_no_key = f"reward_no{i}"
            reward_amount_key = f"reward_amount{i}"
            
            if reward_no := mail.get(reward_no_key):
                amount = mail.get(reward_amount_key, 0)
                item_name = get_item_name(data, reward_no)
                if item_name and amount:
                    rewards.append(f"{item_name} x{amount}")
        
        # 构建事件信息
        event_info = []
        event_info.append(f"【邮箱事件】")  # 使用统一的格式
        event_info.append(f"名称：{sender_name_tw}的信件")  # 添加名称行以统一格式
        event_info.append(f"标题：{title_tw}")
        event_info.append(f"描述：{desc_tw}")
        event_info.append(f"持续时间：{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
        
        if rewards:
            event_info.append("奖励：")
            event_info.extend([f"- {reward}" for reward in rewards])
        
        mail_events.append((start_date, "\n".join(event_info)))
    
    return mail_events


def get_calendar_events(data, target_month, current_year):
    """获取一般活动信息"""
    calendar_events_with_date = []
    now = datetime.now()
    
    for schedule in data["localization_schedule"]["json"]:
        schedule_key = schedule.get("schedule_key", "")
        # 排除特殊事件和主要活动
        if not schedule_key.startswith("Calender_") or \
           schedule_key.startswith("Calender_SingleRaid_") or \
           schedule_key.startswith("Calender_EdenAlliance_") or \
           schedule_key.startswith("Calender_PickUp_") or \
           schedule_key.startswith("Calender_WorldBoss_") or \
           schedule_key.startswith("Calender_GuildRaid_") or \
           schedule_key.endswith("_Main"):
            continue
            
        start_date = schedule.get("start_date")
        end_date = schedule.get("end_date")
        
        if not (start_date and end_date):
            continue
            
        start_date = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
        end_date = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
        
        is_in_month = (
            (start_date.year == current_year and start_date.month == target_month) or
            (end_date.year == current_year and end_date.month == target_month)
        ) and end_date >= now
        
        if not is_in_month:
            continue
            
        event_name_tw = ""
        event_name_cn = ""
        
        # 从EventCalender中获取name_sno
        for event in data["event_calender"]["json"]:
            if event.get("schedule_key") == schedule_key:
                name_sno = event.get("name_sno")
                if name_sno:
                    # 从StringUI中获取名称并处理换行
                    for string in data["string_ui"]["json"]:
                        if string["no"] == name_sno:
                            # 在这里处理换行符
                            event_name_tw = string.get("zh_tw", "").replace('\\r\\n', ' ').replace('\r\n', ' ').replace('\n', ' ')
                            event_name_cn = string.get("zh_cn", "").replace('\\r\\n', ' ').replace('\r\n', ' ').replace('\n', ' ')
                            break
                break
        
        if event_name_tw:
            event_info = []
            event_info.append(f"【活动】")
            event_info.append(f"名称：{event_name_tw}")
            event_info.append(f"持续时间：{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
            calendar_events_with_date.append((start_date, "\n".join(event_info)))
    
    calendar_events_with_date.sort(key=lambda x: x[0])
    return [event_info for _, event_info in calendar_events_with_date]

def get_item_name(data, item_no):
    """获取物品名称"""
    item_name = "未知物品"
    # 在Item.json中查找物品
    for item in data["item"]["json"]:
        if item["no"] == item_no:
            name_sno = item.get("name_sno")
            if name_sno:
                # 在StringItem.json中查找物品名称
                for string in data["string_item"]["json"]:
                    if string["no"] == name_sno:
                        return string.get("zh_tw", "未知物品")
    return item_name


def get_town_object_info(data: dict, hero_id: int) -> list:
    """获取角色专属领地物品信息
    
    Args:
        data: 游戏数据字典
        hero_id: 角色ID
    
    Returns:
        list: 物品信息列表 [(物品编号, 物品名称, 物品品质, 物品类型, 物品描述, 图片路径), ...]
    """
    try:
        objects_info = []
        
        # 在TownObjet.json中查找对应角色的物品
        for obj in data["town_object"]["json"]:
            if obj.get("hero") == hero_id:
                obj_no = obj.get("no")
                if not obj_no:
                    continue
                
                # 获取prefab作为图片名称
                prefab = obj.get("prefab", "")
                    
                # 在Item.json中查找对应物品信息
                for item in data["item"]["json"]:
                    if item.get("no") == obj_no:
                        # 获取物品名称
                        name = ""
                        name_sno = item.get("name_sno")
                        if name_sno:
                            for string in data["string_item"]["json"]:
                                if string.get("no") == name_sno:
                                    name = string.get("zh_tw", "")
                                    break
                        
                        # 获取物品品质
                        grade = ""
                        grade_sno = item.get("grade_sno")
                        if grade_sno:
                            for string in data["string_system"]["json"]:
                                if string.get("no") == grade_sno:
                                    grade = string.get("zh_tw", "")
                                    break
                        
                        # 获取物品类型
                        slot_type = ""
                        slot_limit_sno = item.get("slot_limit_sno")
                        if slot_limit_sno:
                            for string in data["string_ui"]["json"]:
                                if string.get("no") == slot_limit_sno:
                                    slot_type = string.get("zh_tw", "")
                                    break
                        
                        # 获取物品描述并清理颜色标签
                        desc = ""
                        desc_sno = item.get("desc_sno")
                        if desc_sno:
                            for string in data["string_item"]["json"]:
                                if string.get("no") == desc_sno:
                                    desc = clean_color_tags(string.get("zh_tw", ""))  # 使用clean_color_tags清理颜色标签
                                    break
                        
                        if name:  # 只添加有名称的物品
                            # 构建图片路径
                            img_path = None
                            if prefab:
                                img_path = os.path.join(os.path.dirname(__file__), "town", f"{prefab}.png")
                                if not os.path.exists(img_path):
                                    img_path = None
                            
                            objects_info.append((obj_no, name, grade, slot_type, desc, img_path))
                        
        return objects_info
        
    except Exception as e:
        logger.error(f"获取专属领地物品信息时发生错误: {e}, hero_id={hero_id}")
        return []
    
def get_town_object_tasks(data: dict, obj_no: int) -> list:
    """获取专属领地物品可进行的任务信息
    
    Args:
        data: 游戏数据字典
        obj_no: 物品编号
    
    Returns:
        list: 任务信息列表
    """
    try:
        tasks_info = []
        
        # 特性名称映射
        trait_names = {
            "conversation": "口才",
            "culture": "教养",
            "courage": "胆量",
            "knowledge": "知识",
            "guts": "毅力",
            "handicraft": "才艺"
        }
        
        # 在ArbeitChoice中查找对应物品的任务
        for choice in data["arbeit_choice"]["json"]:
            if choice.get("objet_no") == obj_no:
                arbeit_no = choice.get("arbeit_no")
                if not arbeit_no:
                    continue
                
                # 在ArbeitList中查找任务详情
                for arbeit in data["arbeit_list"]["json"]:
                    if arbeit.get("no") == arbeit_no:
                        # 获取任务品质
                        rarity = ""
                        rarity_sno = arbeit.get("rarity")
                        if rarity_sno:
                            for string in data["string_system"]["json"]:
                                if string.get("no") == rarity_sno:
                                    rarity = string.get("zh_tw", "")
                                    break
                        
                        # 获取任务名称
                        name = ""
                        name_sno = arbeit.get("name_sno")
                        if name_sno:
                            for string in data["string_town"]["json"]:
                                if string.get("no") == name_sno:
                                    name = string.get("zh_tw", "")
                                    break
                        
                        # 获取所需时间
                        time_hours = arbeit.get("time", 0) / 3600
                        
                        # 获取要求特性
                        traits = []
                        for trait, zh_name in trait_names.items():
                            if stars := arbeit.get(trait):
                                traits.append(f"{zh_name}{stars}★")
                        
                        # 获取奖励物品
                        rewards = []
                        for i in range(1, 3):  # 检查item1和item2
                            item_no = arbeit.get(f"item{i}_no")
                            item_amount = arbeit.get(f"item{i}_amount")
                            if item_no and item_amount:
                                # 查找物品名称
                                for item in data["item"]["json"]:
                                    if item.get("no") == item_no:
                                        name_sno = item.get("name_sno")
                                        if name_sno:
                                            for string in data["string_item"]["json"]:
                                                if string.get("no") == name_sno:
                                                    item_name = string.get("zh_tw", "")
                                                    rewards.append(f"{item_name} x{item_amount}")
                                                    break
                        
                        # 添加任务信息
                        tasks_info.append({
                            "name": name,
                            "rarity": rarity,
                            "time": time_hours,
                            "traits": traits,
                            "stress": arbeit.get("stress", 0),
                            "exp": arbeit.get("arbeit_exp", 0),
                            "rewards": rewards
                        })
                        
        return tasks_info
        
    except Exception as e:
        logger.error(f"获取专属物品任务信息时发生错误: {e}, obj_no={obj_no}")
        return []


def load_data_source_config():
    """加载数据源配置"""
    try:
        if DATA_SOURCE_CONFIG.exists():
            with open(DATA_SOURCE_CONFIG, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                # 确保配置完整
                if all(key in config for key in DEFAULT_CONFIG):
                    # 转换路径字符串为Path对象
                    config["json_path"] = Path(config["json_path"])
                    config["hero_alias_file"] = Path(config["hero_alias_file"])
                    return config
    except Exception as e:
        logger.error(f"加载数据源配置出错: {e}")
    
    # 如果出错或配置不存在，使用默认配置
    return DEFAULT_CONFIG.copy()

def save_data_source_config(config):
    """保存数据源配置"""
    try:
        # 转换Path对象为字符串以便序列化
        save_config = config.copy()
        save_config["json_path"] = str(config["json_path"])
        save_config["hero_alias_file"] = str(config["hero_alias_file"])
        
        with open(DATA_SOURCE_CONFIG, "w", encoding="utf-8") as f:
            yaml.dump(save_config, f, allow_unicode=True)
    except Exception as e:
        logger.error(f"保存数据源配置出错: {e}")


def get_cash_item_info(data: dict, item_type: str, gate_info: dict) -> list:
    """获取突发礼包信息
    
    Args:
        data: 游戏数据字典
        item_type: 礼包类型 ('barrier'/'stage'/'tower'/'grade_eternal')
        gate_info: 关卡/角色信息字典
    
    Returns:
        list: 包含礼包信息的消息列表
    """
    messages = []
    shop_items = []
    
    # 获取礼包类型显示名称
    package_types = {
        'barrier': '通关礼包',
        'stage': '主线礼包',
        'tower': '起源之塔礼包',
        'grade_eternal': '角色升阶礼包'
    }
    package_type_name = package_types.get(item_type, '特殊礼包')
    
    # 获取符合条件的商店物品
    for shop_item in data["cash_shop_item"]["json"]:
        if shop_item.get("type") == item_type and shop_item.get("type_value") == str(gate_info["no"]):
            shop_items.append(shop_item)
    
    if shop_items:
        for shop_item in shop_items:
            package_info = []
            package_info.append(f"\n【{package_type_name}】")
            package_info.append("▼ " + "-" * 20)
            
            # 获取礼包名称和描述
            name_sno = shop_item.get("name_sno")
            package_name = next((s.get("zh_tw", "未知礼包") for s in data["string_cashshop"]["json"] 
                               if s["no"] == name_sno), "未知礼包")
            
            info_sno = shop_item.get("item_info_sno")
            package_desc = next((s.get("zh_tw", "") for s in data["string_cashshop"]["json"] 
                               if s["no"] == info_sno), "")
            
            desc_sno = shop_item.get("desc_sno")
            limit_desc = next((s.get("zh_tw", "").format(shop_item.get("limit_buy", 0)) 
                             for s in data["string_ui"]["json"] if s["no"] == desc_sno), "")
            
            # 基本信息部分
            basic_info = [
                f"礼包名称：{package_name}"
            ]
            if package_desc:
                basic_info.append(f"礼包描述：{package_desc}")
            basic_info.extend([
                f"购买限制：{limit_desc}",
                f"剩余时间：{shop_item.get('limit_hour', 0)}小时"
            ])
            package_info.append("\n".join(basic_info))
            
            # 礼包内容部分
            content_info = []
            if item_infos := shop_item.get("item_infos"):
                try:
                    items = ast.literal_eval(item_infos)
                    content_info.append("\n礼包内容：")
                    for item_no, amount in items:
                        item_name = get_item_name(data, item_no)
                        content_info.append(f"· {item_name} x{amount}")
                except Exception as e:
                    logger.error(f"解析礼包内容时发生错误：{e}")
            if content_info:
                package_info.append("\n".join(content_info))
            
            # 价格信息部分
            price_info = ["\n价格信息："]
            if price_krw := shop_item.get("price_krw"):
                price_info.append(f"· {price_krw}韩元")
            if price_other := shop_item.get("price_other"):
                price_info.append(f"· {price_other}日元")
            package_info.append("\n".join(price_info))
            
            # 添加分隔线
            package_info.append("-" * 25)
            
            # 将整个礼包信息作为一条消息添加到列表中
            messages.append("\n".join(package_info))
    
    return messages


def get_drop_items(data, group_no):
    """获取掉落物品信息，并去重保留最高概率
    
    Args:
        data: JSON数据字典
        group_no: 掉落组编号
    
    Returns:
        list: [(物品名称, 数量, 掉落率)] 的列表
    """
    drop_items_dict = {}  # 用字典存储物品信息，键为物品名称
    
    # 获取所有符合条件的掉落组
    for drop_group in data["item_drop_group"]["json"]:
        if drop_group["no"] <= group_no:
            item_no = drop_group.get("item_no")
            amount = drop_group.get("amount", 0)
            drop_rate = drop_group.get("drop_rate", 0)
            
            if item_no:
                item_name = get_item_name(data, item_no)
                # 转换掉落率 (1 = 0.001%)
                rate_percent = drop_rate * 0.001
                
                # 如果物品已存在，比较掉落率
                if item_name in drop_items_dict:
                    old_amount, old_rate = drop_items_dict[item_name]
                    # 只有当新的掉落率更高时才更新
                    if rate_percent > old_rate:
                        drop_items_dict[item_name] = (amount, rate_percent)
                else:
                    # 新物品直接添加
                    drop_items_dict[item_name] = (amount, rate_percent)
    
    # 将字典转换为列表
    drop_items = [(name, amount, rate) 
                  for name, (amount, rate) in drop_items_dict.items()]
    
    # 按掉落率从高到低排序
    return sorted(drop_items, key=lambda x: (-x[2], x[0]))

def get_affection_cgs(data, hero_id):
    """获取角色好感CG
    
    Args:
        data: JSON数据字典
        hero_id: 角色ID
    
    Returns:
        list: [(图片路径, CG编号)] 的列表
    """
    cg_path = Path(__file__).parent / "cg"
    if not cg_path.exists():
        return []
    
    # 将hero_id转换为act格式
    act = hero_id
    
    # 收集所有相关的故事编号
    story_nos = set()
    for story in data["story_info"]["json"]:
        if "act" in story and story["act"] == act:
            story_nos.add(story["no"])
    
    # 从Illust.json中获取CG信息
    cg_info = []
    for illust in data["illust"]["json"]:
        if ("open_condition" in illust and 
            illust["open_condition"] in story_nos and 
            "bg_movie_path" in illust):
            # 从路径中提取CG名称
            path_parts = illust["bg_movie_path"].split('/')
            cg_name = path_parts[-1]
            cg_info.append((illust["no"], cg_name))
    
    # 查找匹配的CG图片
    images = []
    for no, cg_name in sorted(cg_info):  # 按编号排序
        for file in cg_path.glob(f"{cg_name}.*"):
            images.append((file, f"CG_{no}"))
            break  # 找到一个匹配的文件就跳出
    
    return images


def get_skill_value(data, value_id, value_type="VALUE"):
    """处理技能数值
    
    Args:
        data: JSON数据字典
        value_id: 技能ID
        value_type: 值类型（"VALUE" 或 "DURATION"）
    """
    # 如果是DURATION类型，需要从SkillCode和SkillBuff中获取
    if value_type == "DURATION":
        # 先检查SkillCode中的value
        for code in data["skill_code"]["json"]:
            if code["no"] == value_id:
                value_without_decimal = int(code["value"]) if code["value"].is_integer() else code["value"]
                # 在SkillBuff中查找对应的duration
                for buff in data["skill_buff"]["json"]:
                    if buff["no"] == value_without_decimal:
                        return str(int(abs(buff["duration"])))  # 返回duration值
        
        # 如果在SkillCode中没找到，直接查找SkillBuff
        for buff in data["skill_buff"]["json"]:
            if buff["no"] == value_id:
                return str(int(abs(buff["duration"])))  # 取绝对值
        return "???"

    # 从SkillCode.json中查找数值
    for code in data["skill_code"]["json"]:
        if code["no"] == value_id:
            # 检查value是否为整数形式（去掉.0后）的数字
            value_without_decimal = int(code["value"]) if code["value"].is_integer() else code["value"]
            
            # 如果value（去掉.0后）等于另一个no，则从SkillBuff中查找这个no的值
            if isinstance(value_without_decimal, int):
                for buff in data["skill_buff"]["json"]:
                    if buff["no"] == value_without_decimal:
                        value = abs(buff["value"])  # 取绝对值
                        if value >= 50:  # 5000%
                            return str(int(value))
                        else:
                            # 检查百分比值是否为整数
                            percent_value = value * 100
                            if percent_value.is_integer():
                                return f"{int(percent_value)}%"
                            return f"{percent_value:.1f}%"
            
            # 如果不是引用其他no，则直接使用code中的value
            value = abs(code["value"])  # 取绝对值
            # 当值小于等于50时按百分比处理
            if value <= 50:
                # 检查百分比值是否为整数
                percent_value = value * 100
                if percent_value.is_integer():
                    return f"{int(percent_value)}%"
                # 如果不是整数，检查小数点后是否为0
                formatted_value = f"{percent_value:.1f}"
                if formatted_value.endswith('.0'):
                    return f"{int(percent_value)}%"
                return f"{formatted_value}%"
            # 大于50的值按整数处理
            return str(int(value))
    return "???"


def process_skill_description(data, description):
    """处理技能描述中的数值标签"""
    def replace_value(match):
        value_id = int(match.group(1))
        value_type = match.group(2)
        return get_skill_value(data, value_id, value_type)
    
    # 替换所有形如 <数字.VALUE> 或 <数字.DURATION> 的内容
    processed_desc = re.sub(r'<\s*(\d+)\.(VALUE|DURATION)\s*>', replace_value, description)
    return processed_desc

def get_skill_info(data, skill_no, is_support=False, hero_data=None):
    """获取技能信息
    
    Args:
        data: JSON数据字典
        skill_no: 技能编号
        is_support: 是否为支援技能
        hero_data: 英雄数据（用于获取辅助伙伴技能信息）
    
    Returns:
        tuple: (技能名称, 技能描述列表, 技能图标信息, 是否为支援技能)
    """
    skill_data_list = []
    skill_name_zh_tw = ""
    skill_name_zh_cn = ""
    skill_name_kr = ""
    skill_name_en = ""
    skill_descriptions = []
    skill_icon_info = None
    
    # 查找所有相同编号的技能数据
    for skill in data["skill"]["json"]:
        if skill["no"] == skill_no:
            skill_data_list.append(skill)
            # 只在第一次找到技能时获取图标信息
            if not skill_icon_info:
                icon_prefab = skill.get("icon_prefab")
                if icon_prefab == 14:
                    skill_icon_info = {
                        "icon": "Icon_Sub_Change",
                        "color": "#e168eb"
                    }
                elif icon_prefab:
                    for icon_data in data["skill_icon"]["json"]:
                        if icon_data["no"] == icon_prefab:
                            skill_icon_info = {
                                "icon": icon_data["icon"],
                                "color": f"#{icon_data['color']}"
                            }
                            break
    
    if skill_data_list:
        # 获取技能名称
        for string in data["string_skill"]["json"]:
            if string["no"] == skill_data_list[0]["name_sno"]:
                skill_name_zh_tw = string.get("zh_tw", "")
                skill_name_zh_cn = string.get("zh_cn", "")
                skill_name_kr = string.get("kr", "")
                skill_name_en = string.get("en", "")
                break
        
        if is_support:
            # 找出最高等级的技能数据
            max_level_skill = max(skill_data_list, key=lambda x: x.get("level", 0))
            
            # 获取主要伙伴技能描述
                        # 获取主要伙伴技能描述
            for string in data["string_skill"]["json"]:
                if string["no"] == max_level_skill["tooltip_sno"]:
                    desc_tw = string.get("zh_tw", "")
                    desc_cn = string.get("zh_cn", "")
                    desc_kr = string.get("kr", "")
                    desc_en = string.get("en", "")
                    # 清理颜色标签
                    desc_tw = clean_color_tags(desc_tw)
                    desc_cn = clean_color_tags(desc_cn)
                    desc_kr = clean_color_tags(desc_kr)
                    desc_en = clean_color_tags(desc_en)
                    # 处理数值标签
                    desc_tw = process_skill_description(data, desc_tw)
                    desc_cn = process_skill_description(data, desc_cn)
                    desc_kr = process_skill_description(data, desc_kr)
                    desc_en = process_skill_description(data, desc_en)
                    skill_descriptions.append((
                        f"主要夥伴：{desc_tw}",  # 添加主要伙伴标记
                        f"主要伙伴：{desc_cn}",
                        f"메인 파트너：{desc_kr}",
                        f"Main Partner Effect：{desc_en}"
                    ))
                    break
            
            # 如果提供了hero_data，获取辅助伙伴技能描述
            if hero_data:
                sub_class_sno = hero_data.get("sub_class_sno")
                max_grade_sno = hero_data.get("max_grade_sno")
                
                if sub_class_sno and max_grade_sno:
                    # 在WorldRaidPartnerBuff中查找匹配的buff
                    for buff in data["world_raid_partner_buff"]["json"]:
                        if (buff["sub_class"] == sub_class_sno and 
                            buff["grade"] == max_grade_sno):
                            buff_sno = buff.get("buff_sno")
                            buff_no = buff.get("buff_no")
                            
                            if buff_sno and buff_no:
                                # 获取buff数值
                                buff_values = []  # 改用列表存储数值
                                for content_buff in data["contents_buff"]["json"]:
                                    if content_buff.get("no") == buff_no:
                                        # 遍历所有属性，按顺序收集非零数值
                                        for key, value in content_buff.items():
                                            if (isinstance(value, (int, float)) and 
                                                value != 0 and 
                                                key != "no"):  # 排除 no 字段
                                                # 根据数值大小判断是否为百分比
                                                if value <= 50:  # 小于等于50的按百分比处理
                                                    buff_values.append(int(value * 100))
                                                else:  # 大于50的按整数处理
                                                    buff_values.append(int(value))
                                
                                # 在StringUI中查找描述文本
                                for string in data["string_ui"]["json"]:
                                    if string["no"] == buff_sno:
                                        desc_tw = string.get("zh_tw", "")
                                        desc_cn = string.get("zh_cn", "")
                                        desc_kr = string.get("kr", "")
                                        desc_en = string.get("en", "")
                                        
                                        # 正则表达式找出所有占位符
                                        placeholders = re.findall(r'{([^}]+)}', desc_tw)
                                        
                                        # 按顺序替换所有占位符
                                        for i, value in enumerate(buff_values):
                                            if i < len(placeholders):
                                                placeholder = f"{{{placeholders[i]}}}"
                                                desc_tw = desc_tw.replace(placeholder, str(value))
                                                desc_cn = desc_cn.replace(placeholder, str(value))
                                                desc_kr = desc_kr.replace(placeholder, str(value))
                                                desc_en = desc_en.replace(placeholder, str(value))
                                        
                                        skill_descriptions.append((
                                            f"輔助夥伴：{desc_tw}",
                                            f"辅助伙伴：{desc_cn}",
                                            f"서브 파트너：{desc_kr}",
                                            f"Support Effect：{desc_en}"
                                        ))
                                        break
                            break
        else:
            # 非支援技能，获取所有等级的技能描述
            for skill_data in skill_data_list:
                hero_level = skill_data.get("hero_level", 1)  # 获取技能解锁等级
                for string in data["string_skill"]["json"]:
                    if string["no"] == skill_data["tooltip_sno"]:
                        desc_tw = string.get("zh_tw", "")
                        desc_cn = string.get("zh_cn", "")
                        desc_kr = string.get("kr", "")
                        desc_en = string.get("en", "")
                        # 清理颜色标签
                        desc_tw = clean_color_tags(desc_tw)
                        desc_cn = clean_color_tags(desc_cn)
                        desc_kr = clean_color_tags(desc_kr)
                        desc_en = clean_color_tags(desc_en)
                        # 处理数值标签
                        desc_tw = process_skill_description(data, desc_tw)
                        desc_cn = process_skill_description(data, desc_cn)
                        desc_kr = process_skill_description(data, desc_kr)
                        desc_en = process_skill_description(data, desc_en)
                        skill_descriptions.append((desc_tw, desc_cn, desc_kr, desc_en, hero_level))
                        break
    
    return skill_name_zh_tw, skill_name_zh_cn, skill_name_kr, skill_name_en, skill_descriptions, skill_icon_info, is_support

def apply_color_to_icon(icon_path: str, color: str) -> bytes:
    """对图标应用颜色
    
    Args:
        icon_path: 图标文件路径
        color: 十六进制颜色代码 (#RRGGBB)
    
    Returns:
        bytes: 处理后的图片数据
    """
    from PIL import Image
    
    # 打开图片
    with Image.open(icon_path) as img:
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # 将十六进制颜色转换为RGB
        color = color.lstrip('#')
        r, g, b = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        
        # 创建底层彩色图片
        base = Image.new('RGBA', img.size, (r, g, b, 255))
        
        # 将原图作为遮罩覆盖在彩色底图上
        result = Image.alpha_composite(base, img)
        
        # 保存为字节流
        from io import BytesIO
        output = BytesIO()
        result.save(output, format='PNG')
        return output.getvalue()
    

def get_character_release_date(data, hero_id):
    """获取角色实装日期
    
    Args:
        data: JSON数据字典
        hero_id: 角色ID
    
    Returns:
        str: 实装日期，如果未找到则返回None
    """
    for movie in data["promotion_movie"]["json"]:
        if movie.get("hero_check") == hero_id:
            # 只取日期部分，不要时间
            start_date = movie.get("start_date", "").split()[0]
            if start_date and start_date != "2999-12-31":  # 排除默认日期
                return start_date
    return None

def format_date_info(release_date):
    """格式化日期信息"""
    return f"实装日期：{release_date}" if release_date else "实装日期：2023-01-05"


async def generate_timeline_html(month: int, events: list) -> str:
    """生成时间线HTML"""
    # 分离特殊活动、一般活动和邮箱事件
    special_events_with_date = []
    normal_events = []
    mail_events_with_date = []
    
    for event in events:
        if isinstance(event, tuple):
            # 已经带有时间信息的事件
            start_date, event_text = event
            if "【邮箱事件】" in event_text:
                mail_events_with_date.append((start_date, event_text))
            elif "【活动】" not in event_text:
                special_events_with_date.append((start_date, event_text))
        else:
            # 一般活动
            if "【活动】" in event:
                normal_events.append(event)
            elif "【邮箱事件】" in event:
                # 解析时间信息
                lines = event.split('\n')
                for line in lines:
                    if "持续时间：" in line:
                        start_date = datetime.strptime(line.split('至')[0].replace('持续时间：', '').strip(), '%Y-%m-%d')
                        mail_events_with_date.append((start_date, event))
                        break
            else:
                # 解析其他特殊活动时间信息
                lines = event.split('\n')
                for line in lines:
                    if "持续时间：" in line:
                        start_date = datetime.strptime(line.split('至')[0].replace('持续时间：', '').strip(), '%Y-%m-%d')
                        special_events_with_date.append((start_date, event))
                        break
    
    # 按时间排序
    special_events_with_date.sort(key=lambda x: x[0])
    mail_events_with_date.sort(key=lambda x: x[0])
    special_events = [event for _, event in special_events_with_date]
    mail_events = [event for _, event in mail_events_with_date]
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: "Microsoft YaHei", Arial, sans-serif;
                margin: 20px;
                background-color: #ffffff;
            }}
            .timeline-container {{
                max-width: 1600px;
                margin: 0 auto;
                display: flex;
                flex-direction: column;
            }}
            .title {{
                color: #333;
                font-size: 24px;
                margin-bottom: 30px;
                text-align: center;
            }}
            .content-container {{
                display: flex;
                gap: 20px;
                justify-content: center;
            }}
            .column {{
                flex: 1;
                max-width: 520px;  /* 调整每列的最大宽度 */
            }}
            .column-title {{
                color: #333;
                font-size: 18px;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 2px solid #eee;
            }}
            .event {{
                margin-bottom: 20px;
                padding: 15px 15px 15px 20px;
                background-color: #ffffff;
                border-radius: 5px;
                position: relative;
            }}
            .event::before {{
                content: '';
                position: absolute;
                left: 0;
                top: 0;
                bottom: 0;
                width: 4px;
                border-radius: 2px;
            }}
            .event-type {{
                display: inline-block;
                padding: 4px 12px;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
                margin-bottom: 10px;
                color: #fff;
            }}

            /* 主要活动 - 玫瑰红 */
            .event.main::before {{
                background-color: #b61274;
            }}
            .event.main .event-type {{
                background-color: #b61274;
            }}
            
            /* Pickup - 紫色 */
            .event.pickup::before {{
                background-color: #6a1b9a;
            }}
            .event.pickup .event-type {{
                background-color: #6a1b9a;
            }}
            
            /* 恶灵讨伐 - 红色 */
            .event.raid::before {{
                background-color: #c62828;
            }}
            .event.raid .event-type {{
                background-color: #c62828;
            }}
            
            /* 联合作战 - 绿色 */
            .event.eden::before {{
                background-color: #2e7d32;
            }}
            .event.eden .event-type {{
                background-color: #2e7d32;
            }}
            
            /* 世界Boss - 橙色 */
            .event.worldboss::before {{
                background-color: #e65100;
            }}
            .event.worldboss .event-type {{
                background-color: #e65100;
            }}
            
            /* 工会突袭 - 棕色 */
            .event.guildraid::before {{
                background-color: #4e342e;
            }}
            .event.guildraid .event-type {{
                background-color: #4e342e;
            }}
            
            /* 邮箱事件 - 青色 */
            .event.mail::before {{
                background-color: #00838f;
            }}
            .event.mail .event-type {{
                background-color: #00838f;
            }}
            
            /* 一般活动 - 深灰色 */
            .event.calendar::before {{
                background-color: #37474f;
            }}
            .event.calendar .event-type {{
                background-color: #37474f;
            }}
            .event-content {{
                color: #333;
                white-space: pre-wrap;
                font-size: 15px;
                line-height: 1.6;
            }}
        </style>
    </head>
    <body>
        <div class="timeline-container">
            <div class="title">{month}月份活动时间线</div>
            <div class="content-container">
                <div class="column">
                    <div class="column-title">特殊活动</div>
                    {''.join([f'''
                    <div class="event {get_event_type_class(event)}">
                        <div class="event-type">{get_event_name(event)}</div>
                        <div class="event-content">{format_event_content(event)}</div>
                    </div>
                    ''' for event in special_events])}
                </div>
                <div class="column">
                    <div class="column-title">一般活动</div>
                    {''.join([f'''
                    <div class="event {get_event_type_class(event)}">
                        <div class="event-type">{get_event_name(event)}</div>
                        <div class="event-content">{format_event_content(event)}</div>
                    </div>
                    ''' for event in normal_events])}
                </div>
                <div class="column">
                    <div class="column-title">邮箱事件</div>
                    {''.join([f'''
                    <div class="event {get_event_type_class(event)}">
                        <div class="event-type">{get_event_name(event)}</div>
                        <div class="event-content">{format_event_content(event)}</div>
                    </div>
                    ''' for event in mail_events])}
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html


def get_event_name(event: str) -> str:
    """提取活动名称"""
    lines = event.split('\n')
    
    # 检查是否是邮件事件
    if lines and "【邮箱事件】" in lines[0]:
        # 从名称行提取发送者名称
        for line in lines:
            if line.startswith("名称："):
                name = line.replace("名称：", "").replace("的信件", "").strip()
                return name
    
    # 其他类型的活动
    for line in lines:
        if line.startswith("名称："):
            # 移除名称前缀，清理特殊字符
            name = line.replace("名称：", "").strip()
            # 处理可能的转义字符和换行
            name = name.replace('\r', '').replace('\n', ' ').replace('\\r', '').replace('\\n', ' ')
            # 合并多个空格
            name = ' '.join(name.split())
            return name
    
    return "未知活动"

def format_event_content(event: str) -> str:
    """格式化事件内容，移除原有的类型标记和名称行"""
    lines = event.split('\n')
    filtered_lines = []
    for line in lines:
        if any(marker in line for marker in [
            "主要活动",
            "活动", 
            "邮箱事件", 
            "恶灵讨伐", 
            "联合作战", 
            "Pickup", 
            "世界Boss", 
            "工会突袭"
        ]) or line.startswith("名称："):
            continue
        filtered_lines.append(line)
    return '\n'.join(filtered_lines)

def get_event_type_class(event: str) -> str:
    """根据事件内容返回对应的CSS类名"""
    if "主要活动" in event:
        return "main"
    elif "活动" in event:
        return "calendar"
    elif "邮箱事件" in event:
        return "mail"
    elif "恶灵讨伐" in event:
        return "raid"
    elif "联合作战" in event:
        return "eden"
    elif "Pickup" in event:
        return "pickup"
    elif "世界Boss" in event:
        return "worldboss"
    elif "工会突袭" in event:
        return "guildraid"
    return "calendar"


def get_potential_value(data: dict, effect_no: int, level: int) -> str:
    """获取潜能数值
    
    Args:
        data: JSON数据字典
        effect_no: 效果编号
        level: 潜能等级
    
    Returns:
        str: 格式化后的数值
    """
    try:
        if str(effect_no).startswith('4'):
            # 从ContentsBuff中获取数值
            for buff in data["contents_buff"]["json"]:
                if buff.get("no") == effect_no:
                    # 遍历所有属性，忽略特定字段
                    ignore_keys = ["no", "battle_power_per", "hero_level_base"]
                    for key, value in buff.items():
                        if key not in ignore_keys and isinstance(value, (int, float)):
                            if value < 1 and key not in ["attack", "defence"]:
                                # 百分比处理
                                return f"{value * 100:.1f}%"
                            else:
                                # 对于attack等属性，如果是小数就保留一位小数
                                if value < 1 and key in ["attack", "defence"]:
                                    return f"{value:.1f}"
                                else:
                                    return str(int(value))
        else:
            # 从SkillBuff中获取数值
            for buff in data["skill_buff"]["json"]:
                if buff.get("no") == effect_no:
                    value = buff.get("value", 0)
                    if value < 1:  # 小于1的按百分比处理
                        return f"{value * 100:.1f}%"
                    else:  # 大于等于1的按整数处理
                        return str(int(value))
    except Exception as e:
        logger.error(f"处理潜能数值时发生错误: {e}, effect_no: {effect_no}, level: {level}")
    return "-"

async def generate_potential_html(data: dict) -> str:
    """生成潜能信息HTML"""
    try:
        # 收集所有潜能信息
        potentials = {}  # {tooltip_sno: [(level, effect_no, option), ...]}
        
        # 从HeroOption中获取所有潜能信息
        for option in data["hero_option"]["json"]:
            tooltip_sno = option.get("tooltip_sno")
            if tooltip_sno:
                if tooltip_sno not in potentials:
                    potentials[tooltip_sno] = []
                potentials[tooltip_sno].append((
                    option.get("level", 0),
                    option.get("effect_no1", 0),
                    option.get("option", 0)
                ))
        
        # 获取潜能名称
        potential_names = {}  # {tooltip_sno: name}
        for string in data["string_ui"]["json"]:
            if string.get("no") in potentials:
                potential_names[string["no"]] = string.get("zh_tw", "未知潜能")
        
        # 生成HTML
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {
                    font-family: "Microsoft YaHei", Arial, sans-serif;
                    margin: 20px;
                    background-color: #ffffff;
                }
                table {
                    border-collapse: collapse;
                    width: 100%;
                    background-color: #ffffff;
                }
                th, td {
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: center;
                }
                th {
                    background-color: #f5f5f5;
                }
                tr:nth-child(even) {
                    background-color: #f9f9f9;
                }
                .title {
                    font-size: 24px;
                    margin-bottom: 20px;
                    text-align: center;
                }
                .potential-name {
                    text-align: left;
                    font-weight: bold;
                }
            </style>
        </head>
        <body>
            <div class="title">潜能数值一览</div>
            <table>
                <tr>
                    <th>潜能名称</th>
        """
        
        # 添加等级列
        max_level = max(level for tooltip_sno in potentials for level, _, _ in potentials[tooltip_sno])
        for level in range(1, max_level + 1):
            html += f"<th>Lv.{level}</th>"
        
        html += "</tr>"
        
        # 添加潜能数据
        for tooltip_sno, name in sorted(potential_names.items(), key=lambda x: x[0]):  # 修改排序键为x[0]
            html += f"<tr><td class='potential-name'>{name}</td>"
            
            # 获取该潜能的所有等级数据
            level_data = {level: (effect_no, option) for level, effect_no, option in potentials[tooltip_sno]}
            
            # 填充每个等级的数值
            for level in range(1, max_level + 1):
                if level in level_data:
                    effect_no, option = level_data[level]
                    value = get_potential_value(data, effect_no, level)
                    html += f"<td>{value}</td>"
                else:
                    html += "<td>-</td>"
            
            html += "</tr>"
        
        html += """
            </table>
        </body>
        </html>
        """
        
        return html
    except Exception as e:
        logger.error(f"生成潜能HTML时发生错误: {e}")
        raise



def get_signature_stats(data, level_group):
    """获取遗物最高等级总属性
    
    Args:
        data: JSON数据字典
        level_group: 遗物等级组ID
    
    Returns:
        dict: 遗物属性统计
    """
    # 找到最高等级的属性数据
    max_level_data = None
    max_level = 0
    
    # 先遍历一遍找出这个遗物的最大等级（40或45）
    for level_data in data["signature_level"]["json"]:
        if level_data["group"] == level_group:
            if level_data["signature_level_"] > max_level:
                max_level = level_data["signature_level_"]
    
    # 再找到最大等级的数据
    for level_data in data["signature_level"]["json"]:
        if level_data["group"] == level_group and level_data["signature_level_"] == max_level:
            max_level_data = level_data
            break
    
    if not max_level_data:
        return []
    
    # 格式化输出文本
    formatted_stats = []
    for stat_key, stat_name in stat_names.items():
        if stat_key in max_level_data and max_level_data[stat_key] != 0:
            value = max_level_data[stat_key]
            if stat_key in ["hit", "dodge"]:
                formatted_stats.append(f"{stat_name}：{int(value)}")
            else:
                # 处理百分比值，使用round避免浮点数精度问题
                percent_value = round(value * 100, 1)
                formatted_value = f"{percent_value:.1f}"
                # 检查是否为整数（包括像29.0这样的值）
                if formatted_value.endswith('.0'):
                    formatted_stats.append(f"{stat_name}：{int(percent_value)}%")
                else:
                    formatted_stats.append(f"{stat_name}：{formatted_value}%")
    
    return formatted_stats, max_level

def get_signature_info(data, hero_id):
    """获取遗物信息
    
    Args:
        data: JSON数据字典
        hero_id: 英雄ID
    
    Returns:
        tuple: (遗物名称, 遗物技能名称, 遗物简介, 遗物技能描述列表)
    """
    signature_data = None
    signature_name_zh_tw = ""
    signature_name_zh_cn = ""
    signature_name_kr = ""
    signature_name_en = ""

    signature_title_zh_tw = ""
    signature_title_zh_cn = ""
    signature_title_kr = ""
    signature_title_en = ""

    signature_desc_zh_tw = ""
    signature_desc_zh_cn = ""
    signature_desc_kr = ""
    signature_desc_en = ""

    skill_descriptions = []
    signature_bg_path = ""
    
    # 在Signature.json中查找对应英雄的遗物
    for signature in data["signature"]["json"]:
        if signature["hero_sno"] == hero_id:
            signature_data = signature
            # 获取遗物图标路径
            if signature_bg_path := signature.get("signature_bg_path"):
                signature_bg_path = f"Img_Signature_{signature_bg_path}.png"
            break
    
    if signature_data:
        # 获取遗物名称
        for string in data["string_skill"]["json"]:
            if string["no"] == signature_data["signature_name_sno"]:
                signature_name_zh_tw = string.get("zh_tw", "")
                signature_name_zh_cn = string.get("zh_cn", "")
                signature_name_kr = string.get("kr", "")
                signature_name_en = string.get("en", "")
                break
        
        # 获取遗物技能名称
        for string in data["string_skill"]["json"]:
            if string["no"] == signature_data["skill_name_sno"]:
                signature_title_zh_tw = string.get("zh_tw", "")
                signature_title_zh_cn = string.get("zh_cn", "")
                signature_title_kr = string.get("kr", "")
                signature_title_en = string.get("en", "")
                break
                
        # 获取遗物简介
        signature_desc_zh_tw = signature_desc_zh_cn = "无遗物简介信息"  # 设置默认值
        signature_desc_kr = "유물 프로필 정보 없음"
        signature_desc_en = "No signature description information"  # 设置默认值
        for string in data["string_skill"]["json"]:
            if string["no"] == signature_data["tooltip_explain_sno"]:
                desc_tw = string.get("zh_tw", "")
                desc_cn = string.get("zh_cn", "")  # 获取简体中文描述
                desc_kr = string.get("kr", "")
                desc_en = string.get("en", "")
                if desc_tw.strip():
                    signature_desc_zh_tw = desc_tw
                if desc_cn.strip():
                    signature_desc_zh_cn = desc_cn
                if desc_kr.strip():
                    signature_desc_kr = desc_kr
                if desc_en.strip():
                    signature_desc_en = desc_en
                break
        
        # 获取所有等级的技能描述
        for i in range(1, 8):  # 1-7级
            sno_key = f"skill_tooltip_sno{i}"
            if sno_key in signature_data:
                tooltip_sno = signature_data[sno_key]
                for string in data["string_skill"]["json"]:
                    if string["no"] == tooltip_sno:
                        desc_tw = string.get("zh_tw", "")
                        desc_cn = string.get("zh_cn", "")  # 获取简体中文描述
                        desc_kr = string.get("kr", "")
                        desc_en = string.get("en", "")
                        # 先清理颜色标签
                        desc_tw = clean_color_tags(desc_tw)
                        desc_cn = clean_color_tags(desc_cn)
                        desc_kr = clean_color_tags(desc_kr)
                        desc_en = clean_color_tags(desc_en)
                        # 处理数值标签
                        desc_tw = process_skill_description(data, desc_tw)
                        desc_cn = process_skill_description(data, desc_cn)
                        desc_kr = process_skill_description(data, desc_kr)
                        desc_en = process_skill_description(data, desc_en)
                        skill_descriptions.append((desc_tw, desc_cn, desc_kr, desc_en))  # 将四种语言的描述作为元组存储
                        break
        
    # 修改返回值，添加图标路径
    if signature_data:
        level_group = signature_data.get("level_group")
        signature_stats = get_signature_stats(data, level_group) if level_group else []
        
        return (signature_name_zh_tw, signature_name_zh_cn, signature_name_kr, signature_name_en, signature_title_zh_tw, signature_title_zh_cn, signature_title_kr, signature_title_en, 
                signature_desc_zh_tw, signature_desc_zh_cn, signature_desc_kr, signature_desc_en, skill_descriptions, signature_stats, signature_bg_path) 
    
    # 如果没有找到遗物数据，返回空值
    return "", "", "", "", "", "", "", "", "", "", "", "", [], [], ""

def get_skill_type(data, type_no):
    """获取技能类型名称
    
    Args:
        data: JSON数据字典
        type_no: 技能类型编号
    
    Returns:
        tuple: (繁中类型名称, 简中类型名称, 韩语类型名称)
    """
    for string in data["string_system"]["json"]:
        if string["no"] == type_no:
            return string.get("zh_tw", "未知类型"), string.get("zh_cn", "未知类型"), string.get("kr", "알수없는유형"), string.get("en", "Unknown type")
    return "未知类型", "未知类型", "알수없는유형", "Unknown type"

def get_string_char(data, sno):
    """从StringCharacter.json中获取文本"""
    for string in data["string_char"]["json"]:
        if string["no"] == sno:
            return string.get("zh_tw", ""), string.get("zh_cn", ""), string.get("kr", ""), string.get("en", "Unknown character")
    return "", "", "", ""


def get_system_string(data, sno):
    for string in data["string_system"]["json"]:
        if string["no"] == sno:
            return string.get("zh_tw", ""), string.get("zh_cn", ""), string.get("kr", ""), string.get("en", "Unknown character")
    return "", "", "", ""

def get_hero_name(data, hero_no):
    """获取角色名称"""
    # 在Hero.json中查找角色
    for hero in data["hero"]["json"]:
        if hero["no"] == hero_no:
            name_sno = hero.get("name_sno")
            if name_sno:
                # 在StringCharacter.json中查找名称
                for char in data["string_char"]["json"]:
                    if char["no"] == name_sno:
                        return char.get("zh_tw", "未知角色"), char.get("zh_cn", "未知角色"), char.get("kr", "알수없는캐릭터"), char.get("en", "Unknown character")
    return "未知角色", "未知角色", "알수없는캐릭터", "Unknown character"

def get_grade_name(data, grade_no):
    """获取阶级名称"""
    for system in data["string_system"]["json"]:
        if system["no"] == grade_no:
            return system.get("zh_tw", "未知阶级"), system.get("zh_cn", "未知阶级"), system.get("kr", "알수없는등급"), system.get("en", "Unknown grade")
    return "未知阶级", "未知阶级", "알수없는등급", "Unknown grade"

def get_formation_type(formation_no):
    """获取阵型类型"""
    formation_types = {
        1: "基本阵型",
        2: "狙击型",
        3: "防守阵型",
        4: "突击型"
    }
    return formation_types.get(formation_no, "未知阵型")


def get_hero_name_by_id(data, hero_id):
    """通过hero_id获取角色名称"""
    # 在Hero.json中查找角色
    for hero in data["hero"]["json"]:
        if hero["no"] == hero_id:  # 使用no而不是hero_id
            name_sno = hero.get("name_sno")
            if name_sno:
                # 在StringCharacter.json中查找名称
                return get_string_char(data, name_sno)
    return "未知角色", "未知角色", "알수없는캐릭터", "Unknown character"

def get_story_info(data, hero_id):
    """获取角色好感故事信息"""
    try:
        # 将hero_id转换为act格式
        act = hero_id
        
        # 收集所有相关的故事信息
        story_episodes = []
        ending_episodes = []
        
        # 从Story_Info中获取所有相关剧情
        for story in data["story_info"]["json"]:
            if ("act" in story and story["act"] == act and 
                "bundle_path" in story and "Story/Love" in story["bundle_path"]):
                if story["episode"] in [8, 9, 10]:
                    ending_episodes.append(story)
                else:
                    story_episodes.append(story)
        
        # 如果没有8-10中的任意一个，则无好感故事
        if not ending_episodes:
            return False, [], {}
        
        # 获取结局信息
        endings = {}
        for episode in ending_episodes:
            if "ending_affinity" in episode:
                if episode["episode"] == 8:
                    endings["bad"] = episode["ending_affinity"]
                elif episode["episode"] == 9:
                    endings["normal"] = episode["ending_affinity"]
                elif episode["episode"] == 10:
                    endings["good"] = episode["ending_affinity"]
        
        # 如果没有找到任何结局信息，返回False
        if not endings:
            return False, [], {}
        
        # 收集每个章节的信息
        episode_info = []
        for episode in story_episodes:
            # 获取选项和好感度
            choices = {}  # 使用字典来按position_type分组
            
            # 先找出所有有好感度的选项的talk_index
            valid_talk_indexes = set()
            for talk in data["talk"]["json"]:
                if talk.get("group_no") == episode.get("talk_group") and "affinity_point" in talk:
                    valid_talk_indexes.add(talk.get("talk_index", 0))
            
            # 收集所有相关选项（包括有好感度和对应talk_index的无好感度选项）
            for talk in data["talk"]["json"]:
                if (talk.get("group_no") == episode.get("talk_group") and 
                    talk.get("talk_index", 0) in valid_talk_indexes):
                    choice_text_zh_tw = ""
                    choice_text_zh_cn = ""
                    choice_text_kr = ""
                    choice_text_en = ""
                    
                    # 安全获取对话文本
                    talk_no = talk.get("no")
                    if talk_no is not None:
                        for string in data["string_talk"]["json"]:
                            if string.get("no") == talk_no:
                                choice_text_zh_tw = string.get("zh_tw", "")
                                choice_text_zh_cn = string.get("zh_cn", "")
                                choice_text_kr = string.get("kr", "")
                                choice_text_en = string.get("en", "")
                                break
                    
                    # 按position_type分组存储选项
                    position_type = talk.get("position_type", 0)
                    if position_type not in choices:
                        choices[position_type] = []
                    choices[position_type].append({
                        "text": choice_text_zh_tw if choice_text_zh_tw != "" else choice_text_kr,
                        "affinity": talk.get("affinity_point", 0),
                        "choice_group": talk.get("choice_group", 0),
                        "no": talk.get("no"),
                        "talk_index": talk.get("talk_index", 0),
                        "group_no": talk.get("group_no")
                    })
            
            # 获取章节标题
            episode_title_zh_tw = ""
            episode_title_zh_cn = ""
            episode_title_kr = ""
            episode_title_en = ""
            episode_name_sno = episode.get("episode_name_sno")
            if episode_name_sno is not None:
                for string in data["string_talk"]["json"]:
                    if string.get("no") == episode_name_sno:
                        episode_title_zh_tw = string.get("zh_tw", "")
                        episode_title_zh_cn = string.get("zh_cn", "")
                        episode_title_kr = string.get("kr", "")
                        episode_title_en = string.get("en", "")
                        break
            
            # 添加章节信息
            episode_info.append({
                "episode": episode.get("episode", 0),
                "title": episode_title_zh_tw if episode_title_zh_tw != "" else episode_title_kr,
                "choices": choices
            })
        
        return True, episode_info, endings
        
    except Exception as e:
        logger.error(f"获取好感故事信息时发生错误: {e}, hero_id={hero_id}")
        return False, [], {}

def format_story_info(episode_info, endings):
    """格式化好感故事信息"""
    # 创建三个结局的信息列表
    good_end = ["好结局攻略："]
    normal_end = ["一般结局攻略："]
    bad_end = ["坏结局攻略："]
    
    # 添加结局条件
    bad_threshold = endings.get('bad', 0)
    normal_threshold = endings.get('normal', 0)
    
    if "bad" in endings:
        good_end.append(f"条件：好感度大于{normal_threshold}")
        normal_end.append(f"条件：好感度{bad_threshold}-{normal_threshold}")
        normal_end.append(f"根据好结局的选项来，然后故意选错一个扣的最高的，好感度在区间内即可")
        bad_end.append(f"条件：好感度低于{bad_threshold}")
    
    # 添加各章节信息
    for ep in episode_info:
        # 收集所有选项
        all_choices = []
        for position_type, choices in ep["choices"].items():
            for choice in choices:
                talk_index = choice.get("talk_index", 0)
                affinity = choice.get("affinity", 0)
                affinity_str = str(affinity) if affinity < 0 else f"+{affinity}" if affinity > 0 else "0"
                
                choice_info = {
                    "talk_index": talk_index,
                    "choice_group": choice["choice_group"],
                    "text": f"（{choice['choice_group']}）{choice['text']}({affinity_str})",
                    "affinity": affinity,
                    "position_type": position_type,
                    "raw_text": choice["text"],
                    "group_no": choice.get("group_no")
                }
                all_choices.append(choice_info)
        
        if not all_choices:
            continue
        
        # 为每个结局添加章节标题
        good_end.append(f"\nEP{ep['episode']}：{ep['title']}")
        bad_end.append(f"\nEP{ep['episode']}：{ep['title']}")

        # 按talk_index排序所有选项
        all_choices.sort(key=lambda x: x["talk_index"])
        
        # 处理好结局选项
        good_choices = []
        current_index = None
        current_group = []
        
        for choice in all_choices:
            if current_index != choice["talk_index"]:
                # 处理上一组的选项
                if current_group:
                    # 找出最高好感度的选项
                    max_affinity = max((c["affinity"] for c in current_group))
                    # 只添加最高好感度的选项
                    for c in current_group:
                        if c["affinity"] == max_affinity:
                            good_choices.append(c["text"]) 
                # 开始新的一组
                current_index = choice["talk_index"]
                current_group = [choice]
            else:
                current_group.append(choice)
        
        # 处理最后一组
        if current_group:
            max_affinity = max((c["affinity"] for c in current_group))
            for c in current_group:
                if c["affinity"] == max_affinity:
                    good_choices.append(c["text"]) 
        
        good_end.extend(good_choices)
        
        # 处理坏结局选项
        bad_choices = []
        current_index = None
        current_group = []
        
        for choice in all_choices:
            if current_index != choice["talk_index"]:
                # 处理上一组的选项
                if current_group:
                    # 首先查找是否有负数好感度的选项
                    min_affinity = min((c["affinity"] for c in current_group))
                    if min_affinity < 0:
                        for c in current_group:
                            if c["affinity"] == min_affinity:
                                bad_choices.append(c["text"]) 
                    else:
                        # 如果没有负数好感度，查找0好感度的选项
                        zero_choices = [c for c in current_group if c["affinity"] == 0]
                        if zero_choices:
                            for c in zero_choices:
                                bad_choices.append(c["text"]) 
                        else:
                            # 如果既没有负数也没有0，则选择最小的正数好感度
                            min_positive = min((c["affinity"] for c in current_group))
                            for c in current_group:
                                if c["affinity"] == min_positive:
                                    bad_choices.append(c["text"]) 
                
                # 开始新的一组
                current_index = choice["talk_index"]
                current_group = [choice]
            else:
                current_group.append(choice)
        
        # 处理最后一组
        if current_group:
            min_affinity = min((c["affinity"] for c in current_group))
            if min_affinity < 0:
                for c in current_group:
                    if c["affinity"] == min_affinity:
                        bad_choices.append(c["text"]) 
            else:
                zero_choices = [c for c in current_group if c["affinity"] == 0]
                if zero_choices:
                    for c in zero_choices:
                        bad_choices.append(c["text"]) 
                else:
                    min_positive = min((c["affinity"] for c in current_group))
                    for c in current_group:
                        if c["affinity"] == min_positive:
                            bad_choices.append(c["text"]) 
        
        bad_end.extend(bad_choices)

    # 合并所有结局信息
    result = ["好感故事攻略："]
    result.extend([""] + good_end)
    result.extend([""] + normal_end)
    result.extend([""] + bad_end)
    
    return "\n".join(result)

def find_similar_names(query, alias_map):
    """查找相似的角色名称
    
    Args:
        query: 用户输入的查询名称
        alias_map: 别名映射字典
    
    Returns:
        list: 可能匹配的角色信息列表 [(角色名, 别名列表), ...]
    """
    # 创建反向映射：hero_id -> (name, aliases)
    hero_map = {}
    for name, hero_id in alias_map.items():
        if hero_id not in hero_map:
            hero_map[hero_id] = [name, []]
        else:
            if len(hero_map[hero_id][1]) == 0:  # 第一个名字是主名称
                hero_map[hero_id][1].append(name)
            else:
                hero_map[hero_id][1].append(name)
    
    # 收集所有可能的名称（主名称和别名）
    all_names = []
    for name, hero_id in alias_map.items():
        all_names.append(name)
    
    # 使用 difflib 查找相似名称
    similar_names = get_close_matches(query, all_names, n=3, cutoff=0.4)
    
    # 收集匹配到的角色信息
    results = []
    for similar_name in similar_names:
        hero_id = alias_map[similar_name]
        main_name = hero_map[hero_id][0]
        aliases = [alias for alias in hero_map[hero_id][1] if alias != main_name]
        if (main_name, aliases) not in results:
            results.append((main_name, aliases))
    
    return results


@es_help.handle()
async def handle_es_help(bot: Bot, event: Event):
    html = """
    <html>
    <head>
        <style>
            body {
                font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
                padding: 20px;
                background: #f5f5f5;
                color: #333;
            }
            .container {
                background: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }
            h1 {
                color: #2c3e50;
                font-size: 24px;
                margin-bottom: 20px;
                text-align: center;
            }
            .command {
                margin-bottom: 20px;
                padding: 10px;
                border-left: 4px solid #3498db;
                background: #f8f9fa;
            }
            .command-name {
                font-weight: bold;
                color: #2980b9;
                margin-bottom: 5px;
            }
            .usage, .example {
                margin: 5px 0;
                color: #666;
            }
            .example {
                font-style: italic;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>EverSoul 命令列表</h1>
            
            <div class="command">
                <div class="command-name">1. es角色信息 + 角色名</div>
                <div class="usage">用途：查询角色的详细信息</div>
                <div class="example">示例：es角色信息大帝</div>
            </div>

            <div class="command">
                <div class="command-name">2. es角色列表</div>
                <div class="usage">用途：查询所有角色以及别名</div>
                <div class="example">示例：es角色列表</div>
            </div>
            
            <div class="command">
                <div class="command-name">3. es主线信息 + 章节-关卡</div>
                <div class="usage">用途：查询主线关卡的详细信息</div>
                <div class="example">示例：es主线信息31-60</div>
            </div>
            
            <div class="command">
                <div class="command-name">4. es x 月事件</div>
                <div class="usage">用途：查询x月的所有事件</div>
                <div class="example">示例：es1月事件</div>
            </div>
            
            <div class="command">
                <div class="command-name">5. es身高/体重排行</div>
                <div class="usage">用途：查询身高/体重排行</div>
                <div class="example">示例：es身高排行</div>
            </div>
            
            <div class="command">
                <div class="command-name">6. es升级消耗 + 等级</div>
                <div class="usage">用途：查询指定等级的升级消耗</div>
                <div class="example">示例：es升级消耗1000</div>
            </div>
            
            <div class="command">
                <div class="command-name">7. es方舟等级信息 + 等级</div>
                <div class="usage">用途：查询指定方舟等级的信息</div>
                <div class="example">示例：es方舟等级信息500</div>
            </div>
            
            <div class="command">
                <div class="command-name">8. es人类/野兽/妖精/不死/自由传送门信息 + 层数</div>
                <div class="usage">用途：查询传送门信息</div>
                <div class="example">示例：es人类传送门信息10</div>
            </div>

            <div class="command">
                <div class="command-name">9. es突发礼包信息主线[章节]/[种类]传送门/起源塔/升阶</div>
                <div class="usage">用途：查询突发礼包信息</div>
                <div class="example">示例：es突发礼包信息主线31</div>
            </div>

            <div class="command">
                <div class="command-name">10. es礼品信息[品质][类型][种类]</div>
                <div class="usage">用途：查询礼品信息</div>
                <div class="example">示例：es礼品信息白1智力加速</div>
            </div>

            <div class="command">
                <div class="command-name">11. es潜能信息</div>
                <div class="usage">用途：查询潜能信息</div>
                <div class="example">示例：es潜能信息</div>
            </div>
        </div>
    </body>
    </html>
    """
    
    pic = await html_to_pic(html, viewport={"width": 800, "height": 10})
    await es_help.finish(MessageSegment.image(pic))


@es_hero_info.handle()
async def handle_hero_info(bot: Bot, event: Event, args: Message = CommandArg()):
    try:
        # 获取输入的文本并提取角色名
        hero_name = args.extract_plain_text().strip()
        if not hero_name:
            return
            
        # 加载数据
        data = load_json_data()
        
        # 加载别名配置和原始别名数据
        with open(current_data_source["hero_alias_file"], "r", encoding="utf-8") as f:
            aliases_data = yaml.safe_load(f)
        alias_map = load_aliases()
        
        # 尝试从别名映射中获取hero_id
        hero_id = alias_map.get(hero_name)
        if not hero_id and hero_name.isascii():  # 如果是英文名称,尝试小写匹配
            hero_id = alias_map.get(hero_name.lower())
            
        if not hero_id:
            # 如果没有直接匹配,尝试模糊匹配
            all_names = list(alias_map.keys())
            # 对于英文输入,同时在小写版本中搜索
            if hero_name.isascii():
                matches = get_close_matches(hero_name.lower(), [n.lower() if n.isascii() else n for n in all_names], n=1, cutoff=0.6)
            else:
                matches = get_close_matches(hero_name, all_names, n=1, cutoff=0.6)
            if matches:
                # 找到匹配的主名称和别名
                matched_name = matches[0]
                matched_hero_id = alias_map[matched_name]
                
                main_names = {
                    "繁体": None,
                    "简体": None,
                    "韩文": None,
                    "英文": None
                }
                aliases = []
                
                for name, hid in alias_map.items():
                    if hid == matched_hero_id:
                        # 在原始数据中查找这个名称属于哪种语言
                        for hero in aliases_data["names"]:
                            if hero["hero_id"] == matched_hero_id:
                                if name == hero.get("zh_tw_name"):
                                    main_names["繁体"] = name
                                elif name == hero.get("zh_cn_name"):
                                    main_names["简体"] = name
                                elif name == hero.get("kr_name"):
                                    main_names["韩文"] = name
                                elif name == hero.get("en_name"):
                                    main_names["英文"] = name
                                elif name in hero.get("aliases", []):
                                    aliases.append(name)
                
                # 构建响应消息
                response_parts = ["未找到角色 " + hero_name + "\n您是否想查询："]
                
                # 添加各语言名称
                for lang, name in main_names.items():
                    if name:
                        response_parts.append(f"{lang}：{name}")
                
                # 添加别名
                if aliases:
                    response_parts.append(f"别名：{', '.join(aliases)}")
                
                await es_hero_info.finish("\n".join(response_parts))
                return
            else:
                await es_hero_info.finish(f"未找到角色 {hero_name}")
                return
        
        # 查找英雄数据
        hero_data = None
        hero_desc = None
        for hero in data["hero"]["json"]:
            if hero["hero_id"] == hero_id:
                hero_data = hero
                break
        
        # 查找英雄描述数据
        for desc in data["hero_desc"]["json"]:
            if desc["hero_no"] == hero_id:
                hero_desc = desc
                break
        
        if not hero_data:
            await es_hero_info.finish("未找到该角色信息")
            return
            
        # 获取英雄名称
        hero_name_tw = ""
        hero_name_cn = ""
        hero_name_kr = ""
        hero_name_en = ""
        for char in data["string_char"]["json"]:
            if char["no"] == hero_data["name_sno"]:
                hero_name_tw = char.get("zh_tw", "")
                hero_name_cn = char.get("zh_cn", "")
                hero_name_kr = char.get("kr", "")
                hero_name_en = char.get("en", "")
                break

        # 获取实装信息
        release_date = get_character_release_date(data, hero_id)
        date_info = format_date_info(release_date)
        
        # 获取双语版本的基础信息
        race_tw, race_cn, race_kr, race_en = get_system_string(data, hero_data["race_sno"])
        hero_class_tw, hero_class_cn, hero_class_kr, hero_class_en = get_system_string(data, hero_data["class_sno"])
        sub_class_tw, sub_class_cn, sub_class_kr, sub_class_en = get_system_string(data, hero_data["sub_class_sno"])
        stat_tw, stat_cn, stat_kr, stat_en = get_system_string(data, hero_data["stat_sno"])
        grade_tw, grade_cn, grade_kr, grade_en = get_system_string(data, hero_data["grade_sno"])
        
        # 构建消息列表
        messages = []
        
        # 基础信息 - 繁体中文
        nickname_tw = ""
        # nickname_cn = ""
        # nickname_kr = ""
        # nickname_en = ""
        if hero_desc and isinstance(hero_desc, dict):
            nick_name_sno = hero_desc.get("nick_name_sno")
            nickname_tw, nickname_cn, nickname_kr, nickname_en = get_string_char(data, nick_name_sno)
            
        # 繁体中文版本
        basic_info_msg = []
        portrait_path = get_character_portrait(data, hero_id, hero_name_en) # 获取立绘路径
        if portrait_path:
            basic_info_msg.append(MessageSegment.image(f"file:///{str(portrait_path.absolute())}"))
        basic_info_tw = f"""
{nickname_tw if nickname_tw else "無稱號"}
{hero_name_tw}
類型：{race_tw} {hero_class_tw}
攻擊方式：{sub_class_tw}
屬性：{stat_tw}
品質：{grade_tw}
隸屬：{get_string_char(data, hero_desc.get("union_sno", 0))[0] if hero_desc else "???"}
身高：{hero_desc.get("height", "???") if hero_desc else "???"}cm
體重：{hero_desc.get("weight", "???") if hero_desc else "???"}kg
生日：{str(hero_desc.get("birthday", "???"))[:2] if hero_desc else "???"}.{str(hero_desc.get("birthday", "???"))[2:] if hero_desc and hero_desc.get("birthday") else "???"}
星座：{get_string_char(data, hero_desc.get("constellation_sno", 0))[0] if hero_desc else "???"}
興趣：{get_string_char(data, hero_desc.get("hobby_sno", 0))[0] if hero_desc else "???"}
特殊專長：{get_string_char(data, hero_desc.get("speciality_sno", 0))[0] if hero_desc else "???"}
喜歡的東西：{get_string_char(data, hero_desc.get("like_sno", 0))[0] if hero_desc else "???"}
討厭的東西：{get_string_char(data, hero_desc.get("dislike_sno", 0))[0] if hero_desc else "???"}
CV：{get_string_char(data, hero_desc.get("cv_sno", 0))[0] if hero_desc else "???"}
CV_JP：{get_string_char(data, hero_desc.get("cv_jp_sno", 0))[0] if hero_desc else "???"}
{date_info}"""
        basic_info_msg.append(basic_info_tw)
        messages.append("\n".join(str(x) for x in basic_info_msg))

        # 添加立绘
        for char in data["string_char"]["json"]:
            if char["no"] == hero_data["name_sno"]:
                images = get_character_illustration(data, hero_id, hero_name_tw, hero_name_cn)
                if images:
                    image_msg = []
                    image_msg.append("下面是全部立绘：")
                    for img_path, display_name_tw, display_name_cn, condition_tw in images:
                        image_msg.append(f"{display_name_tw}\n解锁条件: {condition_tw}")
                        image_msg.append(MessageSegment.image(f"file:///{str(img_path.absolute())}"))
                    messages.append("\n".join(str(x) for x in image_msg))
                break

        # 获取自我介绍
        introduction_tw = "無自我介紹"
        # introduction_cn = "无自我介绍"
        # introduction_kr = "없는 자기소개"
        # introduction_en = "No self-introduction"
        if hero_desc and isinstance(hero_desc, dict):  # 确保hero_desc存在且是字典
            intro_sno = hero_desc.get("introduction_sno")
            if intro_sno:
                intro_tw, intro_cn, intro_kr, intro_en = get_string_char(data, intro_sno)
                if intro_tw:
                    introduction_tw = intro_tw
                if intro_cn:
                    introduction_cn = intro_cn
                if intro_kr:
                    introduction_kr = intro_kr
                if intro_en:
                    introduction_en = intro_en
        # 添加好感故事信息
        has_story, episode_info, endings = get_story_info(data, hero_id)
        if has_story:
            messages.append(format_story_info(episode_info, endings))
        else:
            messages.append("无好感故事选项攻略")
        

        # 获取角色关键字信息
        messages.append("【角色关键字】")
        
        # 获取所有关键字
        trip_keywords = []
        for trip in data["trip_hero"]["json"]:
            if trip.get("hero_no") == hero_id:
                keyword_info = next((k for k in data["trip_keyword"]["json"] 
                                   if k["no"] == trip.get("keyword_no")), None)
                if keyword_info:
                    # 确定关键字类型和好感度
                    keyword_type = "normal"
                    if not trip.get("favor_point"):
                        keyword_type = "bad"
                    elif trip.get("favor_point") == 2:
                        keyword_type = "good"
                    
                    # 获取好感度加成
                    points = get_keyword_points(data, keyword_type)
                    grade_sno = keyword_info.get("keyword_grade")
                    grade_index = 0
                    if grade_sno == 110012:  # 稀有
                        grade_index = 1
                    elif grade_sno == 110014:  # 史诗
                        grade_index = 2
                    favor_point = points[grade_index]
                        
                    trip_keywords.append({
                        "name": get_keyword_name(data, keyword_info.get("keyword_string")),
                        "grade": get_keyword_grade(data, grade_sno),
                        "type": keyword_type,
                        "favor_point": favor_point,
                        "source": get_keyword_source(
                            data, 
                            keyword_info.get("keyword_source", 0),
                            keyword_info.get("keyword_get_details", 0),
                            hero_id,
                            keyword_info.get("keyword_type")
                        ),
                        "keyword_get_details": keyword_info.get("keyword_get_details")  # 改为保存keyword_get_details
                    })
        
        # 分组显示关键字
        bad_keywords = [k for k in trip_keywords if k["type"] == "bad"]
        good_keywords = [k for k in trip_keywords if k["type"] == "good"]
        
        if bad_keywords or good_keywords:
            keyword_msgs = []
            if bad_keywords:
                keyword_msgs.append("▼ 讨厌的话题")
                for keyword in bad_keywords:
                    msg = f"・{keyword['name']}（{keyword['grade']}，好感度 +{keyword['favor_point']}）"
                    # 添加地点信息
                    if location := get_keyword_location(data, keyword.get("keyword_get_details")):
                        msg += f"\n  地点：{location}"
                    keyword_msgs.append(msg)
            
            if good_keywords:
                if bad_keywords:
                    keyword_msgs.append("")
                keyword_msgs.append("▼ 喜欢的话题")
                # 先显示没有获取条件的关键字
                normal_keywords = [k for k in good_keywords if not k["source"]]
                for keyword in normal_keywords:
                    msg = f"・{keyword['name']}（{keyword['grade']}，好感度 +{keyword['favor_point']}）"
                    # 添加地点信息
                    if location := get_keyword_location(data, keyword.get("keyword_get_details")):  # 修正这里
                        msg += f"\n  地点：{location}"
                    keyword_msgs.append(msg)
                
                # 添加分隔线
                if normal_keywords and any(k["source"] for k in good_keywords):
                    keyword_msgs.append("-" * 30)
                
                # 显示需要解锁的关键字
                for keyword in (k for k in good_keywords if k["source"]):
                    msg = f"・{keyword['name']}（{keyword['grade']}，好感度 +{keyword['favor_point']}）"
                    # 添加地点信息
                    if location := get_keyword_location(data, keyword.get("keyword_get_details")):  # 修正这里
                        msg += f"\n  地点：{location}"
                    if keyword["source"]:
                        msg += f"\n  获取条件：{keyword['source']}"
                    keyword_msgs.append(msg)
            
            messages.append("\n".join(keyword_msgs))

        # 在好感故事之后添加CG
        cg_images = get_affection_cgs(data, hero_id)
        if cg_images:
            cg_msg = []
            cg_msg.append("下面是全部好感CG：")
            for img_path, cg_no in cg_images:
                cg_msg.append(f"{cg_no}:")
                cg_msg.append(MessageSegment.image(f"file:///{str(img_path.absolute())}"))
            messages.append("\n".join(str(x) for x in cg_msg))

        # 添加专属领地物品信息
        town_objects = get_town_object_info(data, hero_id)
        if town_objects:
            objects_msg = ["【专属领地物品】"]
            for obj_no, name, grade, slot_type, desc, img_path in town_objects:
                if img_path and os.path.exists(img_path):
                    objects_msg.append(MessageSegment.image(f"file:///{str(Path(img_path).absolute())}"))
                objects_msg.append(f"名称：{name}")
                if grade:
                    objects_msg.append(f"品质：{grade}")
                if slot_type:
                    objects_msg.append(f"类型：{slot_type}")
                if desc:
                    objects_msg.append(f"描述：{desc}")
                
                # 添加可进行的任务信息
                tasks = get_town_object_tasks(data, obj_no)  # 需要从get_town_object_info传递obj_no
                if tasks:
                    objects_msg.append("\n可进行的打工：")
                    for task in tasks:
                        objects_msg.append(f"▼ {task['name']}（{task['rarity']}）")
                        objects_msg.append(f"所需时间：{task['time']}小时")
                        if task['traits']:
                            objects_msg.append(f"要求特性：{' '.join(task['traits'])}")
                        objects_msg.append(f"疲劳度：{task['stress']}")
                        objects_msg.append(f"打工经验：{task['exp']}")
                        if task['rewards']:
                            objects_msg.append("奖励：")
                            objects_msg.extend(f"・{reward}" for reward in task['rewards'])
                
                objects_msg.append("")  # 添加空行分隔不同物品
            messages.append("\n".join(str(x) for x in objects_msg))

        # 属性信息
        stats_info = f"""基础属性：
攻击力：{int(hero_data.get('attack', 0))} (+{int(hero_data.get('inc_attack', 0))}/级)
防御力：{int(hero_data.get('defence', 0))} (+{int(hero_data.get('inc_defence', 0))}/级)
生命值：{int(hero_data.get('max_hp', 0))} (+{int(hero_data.get('inc_max_hp', 0))}/级)
暴击率：{hero_data.get('critical_rate', 0)*100:.1f}% (+{hero_data.get('inc_critical_rate', 0)*100:.3f}%/级)
暴击威力：{hero_data.get('critical_power', 0)*100:.1f}% (+{hero_data.get('inc_critical_power', 0)*100:.3f}%/级)"""
        messages.append(stats_info)
        
        # 技能信息
        # 获取每个技能的类型
        skill_types = []
        skill_keys = ["skill_no1", "skill_no2", "skill_no3", "skill_no4",  "ultimate_skill_no", "support_skill_no"]
        # 先检查角色有哪些技能
        for skill_key in skill_keys:
            if skill_no := hero_data.get(skill_key):
                for skill in data["skill"]["json"]:
                    if skill["no"] == skill_no:
                        skill_type_zh_tw, skill_type_zh_cn, skill_type_kr, skill_type_en = get_skill_type(data, skill["type"])
                        # 判断是否为支援技能
                        is_support = (skill_key == "support_skill_no")
                        skill_name_zh_tw, skill_name_zh_cn, skill_name_kr, skill_name_en, skill_descriptions, skill_icon_info, is_support = get_skill_info(data, skill_no, is_support, hero_data)
                        skill_types.append((skill_type_zh_tw, skill_type_zh_cn, skill_type_kr, skill_type_en, skill_name_zh_tw, skill_name_zh_cn, skill_name_kr, skill_name_en, skill_descriptions, skill_icon_info, is_support))
                        break
        
        for skill_type_zh_tw, skill_type_zh_cn, skill_type_kr, skill_type_en, skill_name_zh_tw, skill_name_zh_cn, skill_name_kr, skill_name_en, skill_descriptions, skill_icon_info, is_support in skill_types:
            skill_text = []
            # 如果有技能图标，处理并添加
            if skill_icon_info:
                icon_path = os.path.join(os.path.dirname(__file__), "icon", f"{skill_icon_info['icon']}.png")
                temp_icon_path = os.path.join(os.path.dirname(__file__), "temp", f"temp_{skill_icon_info['icon']}.png")
                
                # 检查缓存是否存在
                if os.path.exists(temp_icon_path):
                    # 直接使用缓存的图标
                    skill_text.append(MessageSegment.image(f"file:///{temp_icon_path}"))
                elif os.path.exists(icon_path):
                    # 如果缓存不存在但原图存在，则生成新的彩色图标
                    colored_icon = apply_color_to_icon(icon_path, skill_icon_info['color'])
                    os.makedirs(os.path.dirname(temp_icon_path), exist_ok=True)
                    with open(temp_icon_path, 'wb') as f:
                        f.write(colored_icon)
                    skill_text.append(MessageSegment.image(f"file:///{temp_icon_path}"))
            
                        # 如果是支援技能，使用新的格式
            if is_support:
                # 分类存储主要和辅助效果
                main_effects = []
                support_effects = []
                
                # 对效果进行分类
                for desc_tw, desc_cn, desc_kr, desc_en in skill_descriptions:
                    if "主要伙伴" in desc_cn:
                        main_effects.append(desc_tw.replace("主要夥伴：", ""))
                    elif "辅助伙伴" in desc_cn:
                        support_effects.append(desc_tw.replace("輔助夥伴：", ""))
                
                # 如果有主要效果，添加主要效果部分
                if main_effects:
                    skill_text.append("▼ 主要伙伴效果")
                    skill_text.append(f"【{skill_type_zh_tw}】{skill_name_zh_tw}")
                    skill_text.extend(main_effects)
                
                # 如果有辅助效果，添加辅助效果部分
                if support_effects:
                    skill_text.append("▼ 辅助伙伴效果")
                    if not main_effects:  # 如果之前没有显示过技能名称，在这里显示
                        skill_text.append(f"【{skill_type_zh_tw}】{skill_name_zh_tw}")
                    skill_text.extend(support_effects)
            else:
                # 非支援技能保持原有格式
                skill_text.append(f"【{skill_type_zh_tw}】{skill_name_zh_tw}")
                for i, (desc_tw, desc_cn, desc_kr, desc_en, hero_level) in enumerate(skill_descriptions):
                    unlock_text = f"（等级{hero_level}解锁）" if hero_level >= 1 else ""
                    skill_text.append(f"等级{i+1}：{desc_tw}{unlock_text}\n")
            
            messages.append("\n".join(str(x) for x in skill_text))

        
        # 获取并添加遗物信息
        signature_name_zh_tw, signature_name_zh_cn, signature_name_kr, signature_name_en, signature_title_zh_tw, signature_title_zh_cn, signature_title_kr, signature_title_en, \
        signature_desc_tw, signature_desc_cn, signature_desc_kr, signature_desc_en, signature_descriptions, signature_stats, signature_bg_path = get_signature_info(data, hero_id)
        if signature_name_zh_tw:
            signature_stats, max_level = signature_stats
            signature_img_path = os.path.join(os.path.dirname(__file__), "signature", signature_bg_path)


            # 遗物信息 - 繁中版本
            signature_msg_tw = []
            # 检查图片是否存在并添加
            if os.path.exists(signature_img_path):
                signature_msg_tw.append(MessageSegment.image(f"file:///{signature_img_path}"))
            
            signature_info_tw = f"""【{signature_name_zh_tw}】
{signature_desc_tw}

{max_level}級屬性：
{chr(10).join(signature_stats)}

遺物技能【{signature_title_zh_tw}】：
""" + "\n".join(f"等級{i+1}：{desc_tw}" for i, (desc_tw, desc_cn, desc_kr, desc_en) in enumerate(signature_descriptions))
            signature_msg_tw.append(signature_info_tw)
            messages.append("\n".join(str(x) for x in signature_msg_tw))
        
        # 构建转发消息
        forward_msgs = []
        for msg in messages:
            # 如果消息是字符串，直接添加
            if isinstance(msg, str):
                forward_msgs.append({
                    "type": "node",
                    "data": {
                        "name": "Eversoul Info",
                        "uin": bot.self_id,
                        "content": msg
                    }
                })

        # 如果消息是列表（包含图片），将其合并
            elif isinstance(msg, list):
                forward_msgs.append({
                    "type": "node",
                    "data": {
                        "name": "Eversoul Info",
                        "uin": bot.self_id,
                        "content": "\n".join(str(x) for x in msg)
                    }
                })

        # 发送合并转发消息
        if isinstance(event, GroupMessageEvent):
            await bot.call_api(
                "send_group_forward_msg",
                group_id=event.group_id,
                messages=forward_msgs
            )
        else:
            await bot.call_api(
                "send_private_forward_msg",
                user_id=event.user_id,
                messages=forward_msgs
            )
    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"处理角色信息时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await es_hero_info.finish(f"处理角色信息时发生错误: {str(e)}")


@es_stage_info.handle()
async def handle_stage_info(bot: Bot, event: Event, args: Message = CommandArg()):
    try:
        # 获取参数文本
        stage_text = args.extract_plain_text().strip()
        
        # 检查格式
        match = re.match(r'^(\d+)-(\d+)$', stage_text)
        if not match:
            return
        
        area_no = int(match.group(1))
        stage_no = int(match.group(2))
        
        # 加载数据
        data = load_json_data()
        
        # 查找关卡信息
        main_stage = None
        
        for stage in data["stage"]["json"]:
            if stage.get("area_no") == area_no and stage.get("stage_no") == stage_no:
                if "exp" in stage:
                    main_stage = stage
                    break  # 找到主线关卡就直接跳出
        
        # 优先使用主线关卡，如果没有则使用其他关卡
        stage_data = main_stage
        
        if not main_stage:
            await es_stage_info.finish(f"未找到关卡 {area_no}-{stage_no} 的信息")
            return
        
        # 构建消息
        messages = []

        # 基础信息
        basic_info = []
        basic_info.append(f"关卡 {area_no}-{stage_no} 信息：")
        
        # 获取关卡类型
        level_type = "未知类型"
        for system in data["string_system"]["json"]:
            if system["no"] == stage_data.get("level_type"):
                level_type = system.get("zh_tw", "未知类型")
                break
        basic_info.append(f"关卡类型：{level_type}")
        basic_info.append(f"经验值：{stage_data.get('exp', 0)}")
        messages.append("\n".join(basic_info))
        
        # 固定掉落物品，按组分类
        for i in range(1, 5):  # 检查item_no1到item_no4
            item_key = f"item_no{i}"
            amount_key = f"amount{i}"
            if item_no := stage_data.get(item_key):
                item_name = get_item_name(data, item_no)
                amount = stage_data.get(amount_key, 0)
                messages.append(f"固定掉落物品{i}：\n{item_name} x{amount}")

        # 获取关卡编号
        stage_no = stage_data["no"]

        # 获取主线突发礼包信息
        cash_item_messages = get_cash_item_info(data, "stage", stage_data)
        messages.extend(cash_item_messages)

        # 查找敌方队伍信息
        battle_teams = []
        for battle in data["stage_battle"]["json"]:
            if battle["no"] == stage_no:
                battle_teams.append(battle)
        
        # 如果有敌方队伍信息，添加到消息中
        if battle_teams:
            # 按team_no排序
            battle_teams.sort(key=lambda x: x.get("team_no", 0))
            
            for team in battle_teams:
                team_info = [f"\n敌方队伍 {team.get('team_no', '?')}："]
                team_info.append(f"阵型：{get_formation_type(team.get('formation_type'))}")
                
                # 添加每个角色的信息
                for i in range(1, 6):  # 检查5个角色位置
                    hero_key = f"hero_no{i}"
                    grade_key = f"hero_grade{i}"
                    level_key = f"level{i}"
                    
                    if hero_no := team.get(hero_key):
                        hero_name_tw, hero_name_cn, hero_name_kr, hero_name_en = get_hero_name(data, hero_no)
                        grade_name_tw, grade_name_cn, grade_name_kr, grade_name_en = get_grade_name(data, team.get(grade_key))
                        level = team.get(level_key, 0)
                        
                        team_info.append(f"位置{i}：{hero_name_tw} {grade_name_tw} {level}级")
                
                messages.append("\n".join(team_info))

        # 发送合并转发消息
        forward_msgs = []
        for msg in messages:
            forward_msgs.append({
                "type": "node",
                "data": {
                    "name": "Stage Info",
                    "uin": bot.self_id,
                    "content": msg
                }
            })
        
        if isinstance(event, GroupMessageEvent):
            await bot.call_api(
                "send_group_forward_msg",
                group_id=event.group_id,
                messages=forward_msgs
            )
        else:
            await bot.call_api(
                "send_private_forward_msg",
                user_id=event.user_id,
                messages=forward_msgs
            )
            

    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"处理关卡信息时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await es_stage_info.finish(f"处理关卡信息时发生错误: {str(e)}")


@es_month.handle()
async def handle_es_month(bot: Bot, event: Event):
    try:
        # 获取月份
        month_match = re.match(r"^es(\d{1,2})月事件$", event.get_plaintext())
        if month_match:
            target_month = int(month_match.group(1))
            if not 1 <= target_month <= 12:
                await es_month.finish("请输入正确的月份(1-12)")
                return
        else:
            # 如果是其他别名触发，使用当前月份
            target_month = datetime.now().month
        
        current_year = datetime.now().year
        # 加载数据
        data = load_json_data()
        
        # 收集指定月份的事件
        month_events = []

        main_events = []
        for schedule in data["localization_schedule"]["json"]:
            schedule_key = schedule.get("schedule_key", "")
            if schedule_key.startswith("Calender_") and schedule_key.endswith("_Main"):
                prefix = schedule_key
                main_events.extend(get_schedule_events(data, target_month, current_year,
                                                    prefix, "主要活动"))
        month_events.extend(main_events)
        
        month_events.extend(get_schedule_events(data, target_month, current_year,
                                             "Calender_PickUp_", "Pickup"))
        month_events.extend(get_schedule_events(data, target_month, current_year, 
                                             "Calender_SingleRaid_", "恶灵讨伐"))
        month_events.extend(get_schedule_events(data, target_month, current_year,
                                             "Calender_EdenAlliance_", "联合作战"))
        month_events.extend(get_schedule_events(data, target_month, current_year,
                                             "Calender_WorldBoss_", "世界Boss"))
        month_events.extend(get_schedule_events(data, target_month, current_year,
                                             "Calender_GuildRaid_", "工会突袭"))

        # 获取一般活动事件
        calendar_events = get_calendar_events(data, target_month, current_year)
        month_events.extend(calendar_events)

        # 获取邮箱事件
        mail_events = get_mail_events(data, target_month, current_year)
        month_events.extend(mail_events)
        
        if month_events:
            # 生成HTML
            html = await generate_timeline_html(target_month, month_events)
            
            # 只使用基本必需的参数
            png_pic = await html_to_pic(
                html, 
                viewport={"width": 1800, "height": 10}
            )
            
            # 直接发送bytes数据
            if isinstance(event, GroupMessageEvent):
                await bot.send_group_msg(
                    group_id=event.group_id,
                    message=MessageSegment.image(png_pic)
                )
            else:
                await bot.send_private_msg(
                    user_id=event.user_id,
                    message=MessageSegment.image(png_pic)
                )
        else:
            await es_month.finish(f"{target_month}月份没有事件哦~")
            
    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"处理月度事件查询时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await es_month.finish(f"处理月度事件查询时发生错误: {str(e)}")


@es_stats.handle()
async def handle_es_stats(bot: Bot, event: Event):
    try:
        # 获取匹配的类型（身高或体重）
        stat_type = event.get_plaintext()[2:4]  # 获取"身高"或"体重"
        
        # 加载数据
        data = load_json_data()
        logger.info("数据加载完成")
        
        # 收集角色信息
        stats_info = []
        unknown_stats = []
        
        # 读取hero_aliases.yaml获取角色信息
        with open(current_data_source["hero_alias_file"], "r", encoding="utf-8") as f:
            hero_aliases_data = yaml.safe_load(f)
            
        # 获取names列表
        char_list = hero_aliases_data.get('names', [])
        
        # 遍历角色列表
        for char_data in char_list:
            if isinstance(char_data, dict):  # 确保是字典类型
                hero_id = char_data.get('hero_id')
                if not hero_id:
                    continue
                
                # 获取角色名称
                char_name_tw, char_name_cn, char_name_kr, char_name_en = get_hero_name_by_id(data, hero_id)
                
                # 查找英雄描述数据
                hero_desc = None
                for desc in data["hero_desc"]["json"]:
                    if desc["hero_no"] == hero_id:
                        hero_desc = desc
                        break
                
                # 获取身高或体重信息
                stat_key = "height" if stat_type == "身高" else "weight"
                stat_value = hero_desc.get(stat_key, "???") if hero_desc else "???"
                
                if stat_value != "???":
                    stats_info.append((char_name_tw, stat_value))
                else:
                    unknown_stats.append(char_name_tw)
        
        # 按身高/体重从大到小排序
        stats_info.sort(key=lambda x: x[1], reverse=True)
        
        # 构建消息
        messages = [f"EverSoul 角色{stat_type}排行：\n"]
        
        # 添加已知数据的角色
        if stats_info:
            messages.append(f"【已知{stat_type}】")
            for i, (name, value) in enumerate(stats_info, 1):
                unit = "cm" if stat_type == "身高" else "kg"
                messages.append(f"{i}. {name}: {value}{unit}")
        else:
            messages.append(f"【已知{stat_type}】\n暂无数据")
        
        # 添加未知数据的角色
        if unknown_stats:
            messages.append(f"\n【未知{stat_type}】")
            for i, name in enumerate(unknown_stats, 1):
                messages.append(f"{i}. {name}")
        
        # 发送合并转发消息
        forward_msgs = [{
            "type": "node",
            "data": {
                "name": f"EverSoul {stat_type} Ranking",
                "uin": bot.self_id,
                "content": "\n".join(messages)
            }
        }]
        
        # 发送消息
        if isinstance(event, GroupMessageEvent):
            await bot.call_api(
                "send_group_forward_msg",
                group_id=event.group_id,
                messages=forward_msgs
            )
        else:
            await bot.call_api(
                "send_private_forward_msg",
                user_id=event.user_id,
                messages=forward_msgs
            )
            
    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"处理{stat_type}排行时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await es_stats.finish(f"处理{stat_type}排行时发生错误: {str(e)}")


@es_level_cost.handle()
async def handle_level_cost(bot: Bot, event: Event, matched: Tuple[Any, ...] = RegexGroup()):
    try:
        # 获取目标等级
        target_level = int(matched[0])
        
        # 加载数据
        data = load_json_data()
        
        # 找出最大等级
        max_level = 0
        for item in data["level"]["json"]:
            if level := item.get("level_"):
                max_level = max(max_level, level)
        
        # 如果目标等级超过最大等级，使用最大等级
        if target_level > max_level:
            target_level = max_level
        
        # 查找目标等级的数据
        level_data = None
        next_level_data = None
        for item in data["level"]["json"]:
            if item.get("level_") == target_level:
                level_data = item
            elif item.get("level_") == target_level + 1:
                next_level_data = item
            if level_data and next_level_data:
                break
        
        # 构建消息
        messages = [f"等级 {target_level} (最大等级) 升级消耗统计：\n" if target_level == max_level 
                   else f"等级 {target_level} 升级消耗统计：\n"]
        
        # 添加累计消耗信息
        messages.append("【累计消耗】")
        messages.append(f"金币：{format_number(level_data.get('sum_gold', 0))}")
        messages.append(f"魔力粉尘：{format_number(level_data.get('sum_mana_dust', 0))}")
        if 'sum_mana_crystal' in level_data:
            messages.append(f"魔力水晶：{format_number(level_data.get('sum_mana_crystal', 0))}")
        
        # 如果有下一级数据，添加升级消耗信息
        if next_level_data:
            messages.append(f"\n【升级到 {target_level + 1} 级需要】")
            messages.append(f"金币：{format_number(next_level_data.get('gold', 0))}")
            messages.append(f"魔力粉尘：{format_number(next_level_data.get('mana_dust', 0))}")
            if 'mana_crystal' in next_level_data:
                messages.append(f"魔力水晶：{format_number(next_level_data.get('mana_crystal', 0))}")
        
        # 发送合并转发消息
        forward_msgs = [{
            "type": "node",
            "data": {
                "name": "EverSoul Level Cost",
                "uin": bot.self_id,
                "content": "\n".join(messages)
            }
        }]
        
        # 发送消息
        if isinstance(event, GroupMessageEvent):
            await bot.call_api(
                "send_group_forward_msg",
                group_id=event.group_id,
                messages=forward_msgs
            )
        else:
            await bot.call_api(
                "send_private_forward_msg",
                user_id=event.user_id,
                messages=forward_msgs
            )
            
    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"处理升级消耗查询时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await es_level_cost.finish(f"处理升级消耗查询时发生错误: {str(e)}")


@es_ark_info.handle()
async def handle_ark_info(bot: Bot, event: Event, matched: Tuple[Any, ...] = RegexGroup()):
    try:
        # 获取目标等级
        target_level = int(matched[0])
        
        # 加载数据
        data = load_json_data()
        
        # 存储不同类型的方舟信息
        ark_types = {
            110051: [],  # 主方舟
            110101: [],  # 战士
            110102: [],  # 游侠
            110103: [],  # 斗士
            110104: [],  # 魔法师
            110105: [],  # 辅助
            110106: []   # 捍卫者
        }
        
        # 收集所有符合等级的方舟信息
        for ark in data["ark_enhance"]["json"]:
            if ark.get("core_level") == target_level:
                core_type = ark.get("core_type02")
                if core_type in ark_types:
                    ark_types[core_type].append(ark)
        
        messages = []
        # 添加标题信息
        title_msg = [f"方舟等级 {target_level} 信息："]
        messages.append("\n".join(title_msg))
        
        # 处理每种类型的方舟
        for core_type, arks in ark_types.items():
            if not arks:
                continue
                
            # 获取方舟类型名称
            type_name = next((s.get("zh_tw", "未知类型") for s in data["string_system"]["json"] 
                            if s["no"] == core_type), "未知类型")
            
            ark_msg = []
            ark_msg.append(f"\n【{type_name}】")
            
            for ark in arks:
                # 获取升级材料信息
                item_name = "未知材料"
                for item in data["item"]["json"]:
                    if item["no"] == ark.get("pay_item_no"):
                        item_name = next((s.get("zh_tw", "未知材料") for s in data["string_item"]["json"] 
                                       if s["no"] == item.get("name_sno")), "未知材料")
                        break
                
                ark_msg.append(f"升级消耗：{item_name} x{ark.get('pay_amount', 0)}")
                
                # 获取基础属性加成
                if buff_no := ark.get("contents_buff_no"):
                    found_buff = False
                    for buff in data["contents_buff"]["json"]:
                        if buff.get("no") == buff_no:
                            found_buff = True
                            ark_msg.append("基础属性加成：")
                            for key, value in buff.items():
                                if key in stat_names and value != 0:
                                    if key.endswith('_rate'):
                                        ark_msg.append(f"· {stat_names[key]}：{value*100:.2f}%")
                                    else:
                                        ark_msg.append(f"· {stat_names[key]}：{format_number(value)}")
                    if not found_buff:
                        ark_msg.append("基础属性加成：数据未找到")
                
                # 获取特殊属性加成
                if sp_buff_value := ark.get("sp_buff_value02"):
                    found_buff = False
                    for buff in data["contents_buff"]["json"]:
                        if buff.get("no") == int(sp_buff_value):
                            found_buff = True
                            ark_msg.append("特殊属性加成：")
                            for key, value in buff.items():
                                if key in stat_names and value != 0:
                                    ark_msg.append(f"· {stat_names[key]}：{value*100:.2f}%")
                    if not found_buff:
                        ark_msg.append("特殊属性加成：数据未找到")

                # 获取超频信息
                if overclock_max := ark.get("overclock_max_level"):
                    ark_msg.append(f"\n超频信息：")
                    total_cost = 0
                    for overclock in data["ark_overclock"]["json"]:
                        if overclock.get("overclock_level", 0) <= overclock_max:
                            total_cost += overclock.get("mana_crystal", 0)
                    ark_msg.append(f"最大超频等级：{overclock_max}")
                    ark_msg.append(f"总超频消耗：{format_number(total_cost)} 魔力水晶")
            
            messages.append("\n".join(ark_msg))
        
        # 添加统计图
        chart_msg = []
        chart_msg.append("\n【等级关系统计图】")
        chart = await generate_ark_level_chart(data)
        chart_msg.append(chart)
        messages.append("\n".join(str(x) for x in chart_msg))
        
        # 构建转发消息
        forward_msgs = []
        for msg in messages:
            forward_msgs.append({
                "type": "node",
                "data": {
                    "name": "EverSoul Ark Info",
                    "uin": bot.self_id,
                    "content": msg
                }
            })
        
        # 发送消息
        if isinstance(event, GroupMessageEvent):
            await bot.call_api(
                "send_group_forward_msg",
                group_id=event.group_id,
                messages=forward_msgs
            )
        else:
            await bot.call_api(
                "send_private_forward_msg",
                user_id=event.user_id,
                messages=forward_msgs
            )
            

    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"处理方舟等级信息时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await es_ark_info.finish(f"处理方舟等级信息时发生错误: {str(e)}")


@es_gate.handle()
async def handle_gate_info(bot: Bot, event: Event, matched: Tuple[Any, ...] = RegexGroup()):
    try:
        # 获取传送门类型和关卡编号
        gate_type = matched[0]
        stage_no = int(matched[1])
        
        # 加载数据
        data = load_json_data()
        
        # 从Barrier.json获取传送门基本信息
        barrier_info = None
        for barrier in data["barrier"]["json"]:
            if barrier.get("stage_type") == GATE_TYPES[gate_type]:
                barrier_info = barrier
                break
        
        if not barrier_info:
            await es_gate.finish(f"未找到{gate_type}型传送门信息")
            return
            
        # 获取传送门名称和限制
        gate_name = next((s.get("zh_tw", "未知") for s in data["string_stage"]["json"] 
                         if s["no"] == barrier_info.get("text_name_sno")), "未知")
        race_restriction = next((s.get("zh_tw", "") for s in data["string_system"]["json"] 
                               if s["no"] == barrier_info.get("restrictions_race_sno")), "")
        
        # 获取开放日期
        open_days = barrier_info.get("open_day", "").split(",")
        day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        open_days_str = "、".join(day_names[int(d)-1] for d in open_days)
        
        # 查找所有对应的传送门信息
        gate_infos = []
        for stage in data["stage"]["json"]:
            if stage.get("stage_type") == GATE_TYPES[gate_type] and stage.get("stage_no") == stage_no:
                gate_infos.append(stage)
        
        if not gate_infos:
            await es_gate.finish(f"未找到编号为 {stage_no} 的{gate_type}传送门")
            return
        
        # 对每个传送门生成信息
        all_messages = []

        # 添加传送门基本信息
        all_messages.append(f"━━━━━━━━━━━━━━━\n{gate_name}\n━━━━━━━━━━━━━━━")
        all_messages.append(f"开放日期：{open_days_str}")
        if race_restriction:
            all_messages.append(f"限制种族：{race_restriction}")
        all_messages.append("━━━━━━━━━━━━━━━\n")
        
        for gate_info in gate_infos:
            messages = []
            
            # 获取关卡名称
            name_sno = gate_info.get("name_sno")
            stage_name = ""
            for string in data["string_stage"]["json"]:
                if string["no"] == name_sno:
                    stage_name = string.get("zh_tw", "未知")
                    stage_name = stage_name.format(stage_no)
                    break
                    
            messages.append(f"━━━━━━━━━━━━━━━\n{stage_name}\n━━━━━━━━━━━━━━━")
            
            # 获取奖励信息
            rewards = []
            for i in range(1, 3):
                item_no = gate_info.get(f"item_no{i}")
                amount = gate_info.get(f"amount{i}")
                if item_no and amount:
                    item_name = get_item_name(data, item_no)
                    rewards.append(f"· {item_name} x{amount}")
            
            if rewards:
                messages.append("\n【通关奖励】")
                messages.extend(rewards)
            
            # 获取通关礼包信息
            cash_item_messages = get_cash_item_info(data, "barrier", gate_info)
            messages.extend(cash_item_messages)
            
            # 获取敌方队伍信息
            battle_teams = []
            for battle in data["stage_battle"]["json"]:
                if battle["no"] == gate_info["no"]:
                    battle_teams.append(battle)
            
            if battle_teams:
                battle_teams.sort(key=lambda x: x.get("team_no", 0))
                for team in battle_teams:
                    messages.append(f"\n【敌方队伍 {team.get('team_no', '?')}】")
                    messages.append(f"▼ 阵型：{get_formation_type(team.get('formation_type'))}")
                    
                    # 添加每个角色的信息
                    for i in range(1, 6):
                        hero_no = team.get(f"hero_no{i}")
                        if not hero_no:
                            continue
                            
                        hero_name = get_hero_name(data, hero_no)
                        grade_name = get_grade_name(data, team.get(f"hero_grade{i}"))
                        level = team.get(f"level{i}", 0)
                        
                        messages.append(f"\n位置{i}：{hero_name}")
                        messages.append(f"· 等级：{level}")
                        messages.append(f"· 品质：{grade_name}")
                        
                        # 检查装备信息
                        if equip_no := team.get(f"hero_equip{i}"):
                            equip_data = next((e for e in data["stage_equip"]["json"] if e["no"] == equip_no), None)
                            if equip_data:
                                messages.append("· 装备：")
                                for slot in range(1, 5):
                                    if item_no := equip_data.get(f"slot{slot}"):
                                        item_name = get_item_name(data, item_no)
                                        level = equip_data.get(f"level{slot}", 0)
                                        messages.append(f"  - {item_name} Lv.{level}")
                        
                        # 检查终极技能优先级
                        if ult_priority := team.get(f"ultimate_autosetting{i}"):
                            messages.append(f"· 终极技能优先级：{ult_priority}")
                    
                    # 检查遗物信息
                    if sig_level := team.get("signature_level"):
                        messages.append(f"\n· 遗物等级：{sig_level}")
                    if sig_skill_level := team.get("signature_skill_level"):
                        messages.append(f"· 遗物技能等级：{sig_skill_level}")
                    messages.append("-" * 25)
            
            # 添加分隔线
            if gate_info != gate_infos[-1]:
                messages.append("\n" + "=" * 30 + "\n")
            
            all_messages.extend(messages)
        
        # 发送合并转发消息
        forward_msgs = [{
            "type": "node",
            "data": {
                "name": "Gate Info",
                "uin": bot.self_id,
                "content": "\n".join(all_messages)
            }
        }]
        
        if isinstance(event, GroupMessageEvent):
            await bot.call_api(
                "send_group_forward_msg",
                group_id=event.group_id,
                messages=forward_msgs
            )
        else:
            await bot.call_api(
                "send_private_forward_msg",
                user_id=event.user_id,
                messages=forward_msgs
            )
            

    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"处理传送门信息时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await es_gate.finish(f"处理传送门信息时发生错误: {str(e)}")


@es_cash_info.handle()
async def handle_cash_info(bot: Bot, event: Event, args: Message = CommandArg()):
    try:
        # 获取参数文本
        args_text = args.extract_plain_text().strip()
        
        # 检查是否是主线章节
        match_main = re.match(r'^主线(\d+)$', args_text)
        # 检查是否是传送门类型
        match_gate = re.match(r'^(自由|人类|野兽|妖精|不死)传送门$', args_text)
        
        if match_main:
            item_type = "主线"
            chapter = match_main.group(1)
        elif match_gate:
            item_type = "传送门"
            gate_type = match_gate.group(1)
        else:
            if args_text == "主线":
                await es_cash_info.finish("请带上主线章节参数！例如：es突发礼包信息主线21")
                return
            elif args_text == "传送门":
                await es_cash_info.finish("请带上传送门类型参数！例如：es突发礼包信息自由传送门")
                return
            item_type = args_text
            chapter = None
            gate_type = None
        
        # 加载数据
        data = load_json_data()
        messages = []
        
        if item_type == "主线":
            # 获取所有主线关卡信息
            for stage in data["stage"]["json"]:
                if "exp" in stage:  # 确认是主线关卡
                    area_no = stage.get("area_no")
                    # 如果指定了章节，只处理对应章节的关卡
                    if chapter and str(area_no) != chapter:
                        continue
                        
                    stage_no = stage.get("stage_no")
                    # 获取关卡编号
                    stage_no_id = stage.get("no")
                    if stage_no_id:
                        # 构建一个包含no的字典
                        stage_info = {"no": stage_no_id}
                        package_msgs = get_cash_item_info(data, "stage", stage_info)
                        if package_msgs:
                            messages.append(f"\n主线关卡 {area_no}-{stage_no}:")
                            messages.extend(package_msgs)
            
            if not messages:
                chapter_text = f"第{chapter}章" if chapter else "所有章节"
                await es_cash_info.finish(f"当前{chapter_text}没有主线相关的突发礼包")
                return
        
        elif item_type == "传送门":
            # 获取传送门类型对应的stage_type
            stage_type = GATE_TYPES.get(gate_type)
            if not stage_type:
                await es_cash_info.finish(f"未知的传送门类型：{gate_type}")
                return
            
            # 从Barrier.json获取传送门基本信息
            barrier_info = None
            for barrier in data["barrier"]["json"]:
                if barrier.get("stage_type") == stage_type:
                    barrier_info = barrier
                    break
            
            if barrier_info:
                # 获取传送门名称
                gate_name = next((s.get("zh_tw", "未知") for s in data["string_stage"]["json"] 
                                if s["no"] == barrier_info.get("text_name_sno")), "未知")
                messages.append(f"\n{gate_name}:")
                
                # 获取所有对应类型的关卡
                for stage in data["stage"]["json"]:
                    if stage.get("stage_type") == stage_type:
                        stage_no = stage.get("stage_no")
                        # 获取关卡名称
                        name_sno = stage.get("name_sno")
                        stage_name = ""
                        for string in data["string_stage"]["json"]:
                            if string["no"] == name_sno:
                                stage_name = string.get("zh_tw", "未知")
                                stage_name = stage_name.format(stage_no)
                                break
                        
                        # 获取通关礼包信息
                        package_msgs = get_cash_item_info(data, "barrier", stage)  # 直接传入stage对象
                        if package_msgs:
                            messages.append(f"\n{stage_name}:")
                            messages.extend(package_msgs)
            
            if len(messages) <= 1:  # 只有标题没有实际内容
                await es_cash_info.finish(f"当前没有{gate_type}型传送门相关的突发礼包")
                return
        
        elif item_type == "起源塔":
            # 获取所有起源之塔信息
            for tower in data["tower"]["json"]:
                hero_id = tower.get("req_hero")
                tower_no = tower.get("no")
                
                # 获取角色名称
                hero_name = ""
                for hero in data["hero"]["json"]:
                    if hero["hero_id"] == hero_id:
                        for char in data["string_char"]["json"]:
                            if char["no"] == hero["name_sno"]:
                                hero_name = char.get("zh_tw", "")
                                break
                        break
                
                tower_name = f"{hero_name}的起源之塔"
                
                # 查找对应的礼包信息
                tower_packages = []
                for shop_item in data["cash_shop_item"]["json"]:
                    if shop_item.get("type") == "tower":
                        type_values = shop_item.get("type_value", "").split(",")
                        type_values = [v.strip() for v in type_values]
                        if str(tower_no) in type_values:
                            tower_packages.append(shop_item)
                
                if tower_packages:
                    messages.append(f"{tower_name}:")
                    for package in tower_packages:
                        # 构建一个简单的字典来匹配get_cash_item_info的参数要求
                        dummy_info = {"no": tower_no}
                        # 临时保存原始type_value
                        original_type_value = package["type_value"]
                        # 修改type_value以匹配get_cash_item_info的处理逻辑
                        package["type_value"] = str(tower_no)
                        package_msgs = get_cash_item_info(data, "tower", dummy_info)
                        # 还原原始type_value
                        package["type_value"] = original_type_value
                        messages.extend(package_msgs)
                    
        elif item_type == "升阶":
            # 获取所有角色升阶礼包信息
            for shop_item in data["cash_shop_item"]["json"]:
                if shop_item.get("type") == "grade_eternal":
                    # 构建一个简单的字典来匹配get_cash_item_info的参数要求
                    dummy_info = {"no": shop_item.get("type_value")}
                    package_msgs = get_cash_item_info(data, "grade_eternal", dummy_info)
                    if package_msgs:
                        messages.extend(package_msgs)
        
        else:
            await es_cash_info.finish("请输入正确的类型：主线/传送门/起源塔/升阶")
            return
        
        if not messages:
            await es_cash_info.finish(f"当前没有{item_type}相关的突发礼包")
            return
        
        # 发送合并转发消息
        forward_msgs = [{
            "type": "node",
            "data": {
                "name": "EverSoul Overclock Cost",
                "uin": bot.self_id,
                "content": "\n".join(messages)
            }
        }]
        
        # 发送消息
        if isinstance(event, GroupMessageEvent):
            await bot.call_api(
                "send_group_forward_msg",
                group_id=event.group_id,
                messages=forward_msgs
            )
        else:
            await bot.call_api(
                "send_private_forward_msg",
                user_id=event.user_id,
                messages=forward_msgs
            )
            

    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"处理突发礼包信息时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await es_cash_info.finish(f"处理突发礼包信息时发生错误: {str(e)}")


@es_tier_info.handle()
async def handle_tier_info(bot: Bot, event: Event, args: Message = CommandArg()):
    try:
        # 解析参数
        args_text = args.extract_plain_text().strip()
        match = re.match(r'^(白|红\+?)(\d*)(智力|敏捷|力量|共用)(加速|暴击率|防御力|体力|攻击力|回避|暴击威力)$', args_text)
        if not match:
            await es_tier_info.finish("格式错误！请使用如：es礼品信息白1智力加速")
            return
            
        # 获取参数
        grade, level, stat_type, set_type = match.groups()
        
        # 加载数据
        data = load_json_data()

        # 获取品质对应的grade_sno
        grade_map = {"白": "不朽", "红+": "永恆＋"}
        if grade == "红+":
            grade_name = "永恆＋"  # 红+装备直接使用永恆＋
        elif grade == "白" and not level:  # 如果是白色且没有等级
            grade_name = "不朽"
        elif grade == "白" and level:  # 如果是白色且有等级
            grade_name = f"不朽+{level}"
        else:
            grade_name = f"{grade_map[grade]}+{level}"  # 其他装备加上等级
            
        grade_sno = next((s["no"] for s in data["string_system"]["json"] 
                         if s.get("zh_tw") == grade_name), None)
        
        # 获取属性限制对应的stat_limit_sno
        stat_sno = stat_mapping.get(stat_type)
        
        # 获取套装效果对应的set_effect_no
        set_no = effect_mapping.get(set_type)
        set_effect = next((e for e in data["item_set_effect"]["json"] 
                          if e.get("name") == set_no), None)
        
        if not all([grade_sno, stat_sno, set_effect]):
            await es_tier_info.finish("未找到对应的礼品信息")
            return
            
        # 查找符合条件的礼品
        items = []
        for item in data["item"]["json"]:
            if ((item.get("category_sno") == 110002 or item.get("category_sno") == 110078) and 
                item.get("grade_sno") == grade_sno and
                item.get("stat_limit_sno") == stat_sno and
                item.get("set_effect_no") == set_effect["no"]):
                items.append(item)
        
        if not items:
            await es_tier_info.finish("未找到符合条件的礼品")
            return
            
        messages = []
        for item in items:
            try:
                # 获取礼品基本信息
                name = next((s.get("zh_tw", "未知") for s in data["string_item"]["json"] 
                           if s["no"] == item.get("name_sno")), "未知")
                desc = next((s.get("zh_tw", "") for s in data["string_item"]["json"] 
                           if s["no"] == item.get("desc_sno")), "")
                
                # 获取图标路径
                icon_base = item.get("icon_path", "")
                if icon_base:
                    # 构建完整的图片路径
                    icon_path = Path(os.path.join(os.path.dirname(__file__), "tier", f"{icon_base}.png"))
                    # 检查文件是否存在
                    if icon_path.exists():
                        img_msg = MessageSegment.image(f"file:///{str(icon_path.absolute())}")
                    else:
                        img_msg = "[图片未找到]"
                else:
                    img_msg = "[无图片信息]"
                
                 # 获取最高等级的属性信息
                max_stat = max((s for s in data["item_stat"]["json"] 
                              if s.get("no") == item.get("no")), 
                             key=lambda x: x.get("level", 0))
                
                # 获取套装效果
                set2_buff_no = set_effect.get("set2_contentsbuff")
                set4_buff_no = set_effect.get("set4_contentsbuff")
                
                set2_buff = {}
                set4_buff = {}
                
                if set2_buff_no:
                    set2_buff = next((buff for buff in data["contents_buff"]["json"] 
                                    if buff.get("no") == set2_buff_no), {})
                if set4_buff_no:
                    set4_buff = next((buff for buff in data["contents_buff"]["json"] 
                                    if buff.get("no") == set4_buff_no), {})
                
                 # 构建消息
                msg = [
                    f"━━━━━━━━━━━━━━━",
                    str(img_msg),
                    f"【{name}】",
                    f"品质：{grade_name}",
                    f"描述：{desc}",
                    f"\n【最大属性】(等级{max_stat.get('level')})",
                    f"· 满级所需经验：{format_number(max_stat.get('sum_exp', 0))}",
                    f"· 满级战斗力：{format_number(max_stat.get('battle_power', 0))}"
                ]

                # 添加基础属性和额外属性
                base_stats = []
                extra_stats = []

                # 获取所有属性（排除特定键）
                exclude_keys = {"index", "no", "level", "exp", "sum_exp", "battle_power", "battle_power_per"}
                stat_items = [(k, v) for k, v in max_stat.items() 
                             if k not in exclude_keys and v and k in stat_names]
                
                # 前三个是基础属性，之后的是额外属性
                for i, (stat, value) in enumerate(stat_items):
                    stat_display = stat_names[stat]
                    if isinstance(value, float):
                        value_str = f"{value*100:.1f}%"
                    else:
                        value_str = format_number(value)
                        
                    if i < 3:  # 基础属性
                        base_stats.append(f"· {stat_display}：{value_str}")
                    else:  # 额外属性
                        extra_stats.append(f"· {stat_display}：{value_str}")
                
                # 添加基础属性
                if base_stats:
                    msg.append("\n基础属性：")
                    msg.extend(base_stats)
                
                # 添加额外属性
                if extra_stats:
                    msg.append("\n额外增益：")
                    msg.extend(extra_stats)
                
                
                
                # 添加套装效果
                msg.extend([
                    f"\n【套装效果】",
                    f"2件套效果："
                ])
                
                # 添加2件套效果
                has_2set = False
                for stat, value in set2_buff.items():
                    if stat in stat_names and value:
                        has_2set = True
                        stat_display = stat_names[stat]
                        msg.append(f"· {stat_display}：{value*100:.1f}%")
                if not has_2set:
                    msg.append("· 无效果")
                
                # 添加4件套效果
                msg.append(f"4件套效果：")
                has_4set = False
                for stat, value in set4_buff.items():
                    if stat in stat_names and value:
                        has_4set = True
                        stat_display = stat_names[stat]
                        msg.append(f"· {stat_display}：{value*100:.1f}%")
                if not has_4set:
                    msg.append("· 无效果")
                
                msg.append("━━━━━━━━━━━━━━━")
                messages.append("\n".join(msg))
            
            except Exception as e:
                logger.error(f"处理礼品图片时发生错误: {e}")
                continue
        
        # 发送合并转发消息
        forward_msgs = []
        for msg in messages:
            forward_msgs.append({
                "type": "node",
                "data": {
                    "name": "Tier Info",
                    "uin": bot.self_id,
                    "content": msg
                }
            })
        
        if isinstance(event, GroupMessageEvent):
            await bot.call_api(
                "send_group_forward_msg",
                group_id=event.group_id,
                messages=forward_msgs
            )
        else:
            await bot.call_api(
                "send_private_forward_msg",
                user_id=event.user_id,
                messages=forward_msgs
            )
            

    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"处理礼品信息时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await es_tier_info.finish(f"处理礼品信息时发生错误: {str(e)}")


@es_potential_info.handle()
async def handle_potential_info(bot: Bot, event: Event):
    """处理潜能信息查询"""
    try:
        data = load_json_data()
        # 生成潜能信息HTML
        html = await generate_potential_html(data)
        # 转换为图片
        pic = await html_to_pic(html, viewport={"width": 1000, "height": 10})
        await es_potential_info.finish(MessageSegment.image(pic))

    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"处理潜能信息时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await es_potential_info.finish(f"处理潜能信息时发生错误: {str(e)}")


@es_hero_list.handle()
async def handle_hero_list(bot: Bot, event: Event):
    """处理角色列表查询"""
    try:
        # 加载数据
        data = load_json_data()
        
        # 加载别名配置
        aliases_data = {}
        with open(current_data_source["hero_alias_file"], "r", encoding="utf-8") as f:
            aliases_data = yaml.safe_load(f)
        
        if not aliases_data or "names" not in aliases_data:
            await es_hero_list.finish("角色数据加载失败")
            return
            
        # 使用字典存储不同种族的角色
        hero_categories = {}
        
        # 遍历所有角色
        for hero in aliases_data["names"]:
            hero_id = hero["hero_id"]
            name = hero["zh_tw_name"]
            if not name:  # 跳过未知角色
                continue
            
            # 从Hero.json中获取角色种族信息
            hero_data = next((h for h in data["hero"]["json"] if h["hero_id"] == hero_id), None)
            if not hero_data:
                continue
                
            # 获取种族名称
            race_tw, _, _, _ = get_system_string(data, hero_data["race_sno"])
            if not race_tw:
                continue
                
            # 初始化种族分类
            if race_tw not in hero_categories:
                hero_categories[race_tw] = []
            
            # 添加别名信息
            aliases = hero.get("aliases", [])
            alias_text = f"（{', '.join(aliases)}）" if aliases else ""
            
            # 添加角色信息
            hero_info = f"{name}{alias_text}"
            hero_categories[race_tw].append(hero_info)
        
        # 生成转发消息
        forward_msgs = []
        for category, heroes in hero_categories.items():
            if heroes:  # 只显示有角色的分类
                msg = f"【{category}】\n"
                msg += "\n".join(f"· {hero}" for hero in sorted(heroes))  # 按名称排序
                
                forward_msgs.append({
                    "type": "node",
                    "data": {
                        "name": "Character List",
                        "uin": bot.self_id,
                        "content": msg
                    }
                })
        
        # 发送合并转发消息
        if isinstance(event, GroupMessageEvent):
            await bot.call_api(
                "send_group_forward_msg",
                group_id=event.group_id,
                messages=forward_msgs
            )
        else:
            await bot.call_api(
                "send_private_forward_msg",
                user_id=event.user_id,
                messages=forward_msgs
            )
            

    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"处理角色列表时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await es_hero_list.finish(f"处理角色列表时发生错误: {str(e)}")
        
@es_avatar_frame.handle()
async def handle_avatar_frame(bot: Bot, event: Event):
    try:
        # 获取图片路径
        plugin_path = Path(os.path.dirname(os.path.abspath(__file__)))
        img_path = plugin_path / "img"
        bg_path = img_path / "T_Fx_UI_RESONANCE_SlotFairyResonance_00.png"
        frame_path = img_path / "T_Fx_UI_RESONANCE_SlotFairyResonance_01.png"

        # 获取用户图片
        image_urls = []
        # 检查消息中的图片和at
        for seg in event.message:
            if seg.type == "image":
                image_urls.append(seg.data["url"])

        # 检查回复消息中的图片
        if hasattr(event, 'reply') and event.reply:
            for seg in event.reply.message:
                if seg.type == "image":
                    image_urls.append(seg.data["url"])

        if not image_urls:
            await es_avatar_frame.finish("请发送图片、回复带图片的消息或艾特要处理头像的用户！")
            return

        # 下载第一张图片
        async with httpx.AsyncClient(verify=False, timeout=120) as client:
            resp = await client.get(image_urls[0], follow_redirects=True)
            if resp.status_code != 200:
                await es_avatar_frame.finish(f"下载图片失败，HTTP状态码: {resp.status_code}")
                return
            avatar_data = resp.content
        
        # 处理背景图片（染色）
        bg = Image.open(bg_path).convert('RGBA')
        bg_data = bg.getdata()
        new_bg_data = []
        for item in bg_data:
            if item[3] > 0:
                new_bg_data.append((125, 123, 160, item[3]))  # 7d7ba0 转RGB，保持原透明度
            else:
                new_bg_data.append(item)
        bg.putdata(new_bg_data)

        # 处理用户图片
        avatar = Image.open(BytesIO(avatar_data)).convert('RGBA')
        
        # 调整图片大小为512x512
        if avatar.size != (512, 512):
            # 计算缩放比例，保持宽高比
            ratio = 512 / max(avatar.size)
            new_size = tuple(int(dim * ratio) for dim in avatar.size)
            avatar = avatar.resize(new_size, Image.Resampling.LANCZOS)
            
            # 创建512x512的新图像，将调整后的图片居中放置
            new_avatar = Image.new('RGBA', (512, 512), (125, 123, 160, 255))  # 使用背景色填充
            x = (512 - new_size[0]) // 2
            y = (512 - new_size[1]) // 2
            new_avatar.paste(avatar, (x, y))
            avatar = new_avatar

        # 处理图片的透明部分，填充背景色
        avatar_data = avatar.getdata()
        new_avatar_data = []
        for item in avatar_data:
            if item[3] < 255:  # 如果像素有任何透明度
                # 计算混合后的颜色
                alpha_ratio = item[3] / 255.0
                bg_color = (125, 123, 160)  # 背景色 #7d7ba0
                new_color = tuple(
                    int(item[i] * alpha_ratio + bg_color[i] * (1 - alpha_ratio))
                    for i in range(3)
                )
                new_avatar_data.append((*new_color, 255))  # 完全不透明
            else:
                new_avatar_data.append(item)
        avatar.putdata(new_avatar_data)

        # 创建遮罩层
        mask = Image.new('L', (512, 512), 0)
        draw = ImageDraw.Draw(mask)

        # 边界点坐标
        boundary_points = [
            (440, 256), (440, 267), (440, 279), (440, 291), (440, 303),
            (440, 315), (440, 328), (440, 342), (440, 357), (440, 372),
            (431, 383), (421, 393), (411, 402), (402, 411), (392, 420),
            (380, 427), (364, 427), (350, 427), (339, 432), (328, 438),
            (317, 446), (306, 452), (294, 459), (282, 466), (269, 474),
            (256, 474), (242, 474), (228, 474), (214, 474), (199, 474),
            (184, 474), (169, 474), (153, 474), (136, 474), (117, 474),
            (97, 474), (75, 474), (64, 460), (64, 436), (64, 414),
            (64, 395), (64, 377), (64, 361), (64, 346), (64, 331),
            (64, 318), (64, 305), (64, 292), (64, 280), (64, 268),
            (64, 256), (64, 243), (64, 231), (64, 219), (64, 206),
            (64, 193), (64, 180), (64, 165), (64, 150), (66, 135),
            (76, 125), (85, 115), (95, 105), (105, 95), (114, 84),
            (130, 83), (146, 83), (159, 80), (169, 73), (181, 67),
            (192, 60), (204, 53), (216, 46), (228, 39), (241, 33),
            (255, 33), (270, 33), (284, 33), (298, 31), (313, 31),
            (328, 31), (344, 31), (361, 31), (378, 33), (396, 33),
            (418, 31), (440, 33), (440, 59), (440, 82), (440, 103),
            (440, 121), (440, 139), (440, 154), (440, 169), (440, 183),
            (440, 196), (440, 208), (440, 220), (440, 232), (440, 244)
        ]

        # 绘制多边形
        draw.polygon(boundary_points, fill=255)

        # 创建新图层（完全透明）
        result = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
        
        # 按顺序叠加图层
        result.paste(bg, (0, 0), bg)  # 先贴背景
        result.paste(avatar, (0, 0), mask)  # 使用遮罩贴头像
        
        # 处理框架图片（白色部分染色）
        frame = Image.open(frame_path).convert('RGBA')
        frame_data = frame.getdata()
        new_frame_data = []
        for item in frame_data:
            if item[0] > 240 and item[1] > 240 and item[2] > 240 and item[3] > 0:
                new_frame_data.append((113, 99, 152, item[3]))
            else:
                new_frame_data.append(item)
        frame.putdata(new_frame_data)
        
        # 叠加框架
        result.paste(frame, (0, 0), frame)

        # 保存临时文件
        temp_path = plugin_path / "temp"
        temp_path.mkdir(exist_ok=True)
        output_path = temp_path / f"avatar_frame_{int(datetime.now().timestamp())}.png"
        result.save(output_path, 'PNG')

        # 发送结果
        await es_avatar_frame.finish(MessageSegment.image(f"file:///{str(output_path.absolute())}"))
        
        # 删除临时文件
        output_path.unlink()


    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"处理头像框时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await es_avatar_frame.finish(f"处理头像框时发生错误: {str(e)}")


async def run_eversoul(timeout: int = 120) -> Optional[str]:
    bot = get_bot()
    try:
        
        import os
        program_path = "/home/rikka/Eversoul/build/eversoul"
        if not os.path.exists(program_path):
            return None
        
        process = await asyncio.create_subprocess_exec(
            program_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/home/rikka/Eversoul/build"
        )
        
        output_lines = []
        buffer = ""
        start_time = time_module.time()
        
        while True:
            try:
                # 检查总运行时间
                current_time = time_module.time()
                if current_time - start_time > timeout:
                    break
                
                # 读取一块数据
                chunk = await asyncio.wait_for(process.stdout.read(1024), timeout=15.0)
                if not chunk:
                    break
                
                # 解码并处理数据
                try:
                    text = chunk.decode('utf-8', errors='replace')
                    buffer += text
                    
                    # 处理完整的行
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        # 处理回车符
                        line = line.split('\r')[-1].strip()
                        
                        # 修改这里：只过滤包含进度条百分比的行
                        if line:
                            output_lines.append(line)
                            
                except UnicodeDecodeError as e:
                    continue
            except asyncio.TimeoutError:
                if process.returncode is not None:
                    break
                continue
        
        # 修改这里：处理剩余的buffer
        if buffer.strip():
            line = buffer.split('\r')[-1].strip()
            if line:
                output_lines.append(line)
        
        # 确保进程结束
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
        
        return '\n'.join(output_lines) if output_lines else None


    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"执行检查更新时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await bot.finish(f"执行检查更新时发生错误: {str(e)}")


async def check_update_background(group_id: int, event: GroupMessageEvent):
    bot = get_bot()
    try:
        # 发送初始消息并获取消息ID用于后续回复
        initial_msg = await bot.send_group_msg(group_id=group_id, message="开始检查更新，请稍候...", reply=True)
        
        output = await run_eversoul()
        
        if output is None:
            await bot.send_group_msg(
                group_id=group_id,
                message=MessageSegment.reply(initial_msg["message_id"]) + "更新检查执行超时或出现错误，请稍后重试。"
            , reply=True)
            return
        
        # 清理ANSI颜色代码
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_output = ansi_escape.sub('', output)
        
        if not clean_output.strip():
            await bot.send_group_msg(
                group_id=group_id,
                message=MessageSegment.reply(initial_msg["message_id"]) + "未获取到更新检查结果，请稍后重试。"
            , reply=True)
            return
        
        # 生成单条转发消息
        forward_msgs = [{
            "type": "node",
            "data": {
                "name": "EverSoul Update Check",
                "uin": bot.self_id,
                "content": clean_output
            }
        }]
        
        # 发送合并转发消息
        if isinstance(event, GroupMessageEvent):
            await bot.call_api(
                "send_group_forward_msg",
                group_id=event.group_id,
                messages=forward_msgs
            )
        else:
            await bot.call_api(
                "send_private_forward_msg",
                user_id=event.user_id,
                messages=forward_msgs
            )
            
        # 检查是否有Git变更并上传
        try:
            # 设置Git仓库路径
            repo_path = Path("/home/rikka/Eversoul")
            
            # 检查目录是否存在
            if not repo_path.exists() or not repo_path.is_dir():
                await bot.send_group_msg(group_id=group_id, message="错误：Eversoul仓库目录不存在")
                return
                
            # 切换到仓库目录
            os.chdir(repo_path)
            
            # 检查是否有Git变更
            status_result = subprocess.run(
                ["git", "status", "--porcelain"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            if not status_result.stdout.strip():
                # 添加到合并转发消息
                forward_msgs.append({
                    "type": "node",
                    "data": {
                        "name": "EverSoul Git Status",
                        "uin": bot.self_id,
                        "content": "检查完成，没有检测到任何变更，无需上传"
                    }
                })
                
                # 发送更新后的合并转发消息
                if isinstance(event, GroupMessageEvent):
                    await bot.call_api(
                        "send_group_forward_msg",
                        group_id=event.group_id,
                        messages=forward_msgs
                    )
                else:
                    await bot.call_api(
                        "send_private_forward_msg",
                        user_id=event.user_id,
                        messages=forward_msgs
                    )
                return
                
            # 获取变更的文件列表
            changed_files = status_result.stdout.strip().split('\n')
            changed_files_count = len(changed_files)
            
            # 添加所有变更
            add_result = subprocess.run(
                ["git", "add", "."], 
                capture_output=True, 
                text=True
            )
            
            if add_result.returncode != 0:
                forward_msgs.append({
                    "type": "node",
                    "data": {
                        "name": "EverSoul Git Error",
                        "uin": bot.self_id,
                        "content": f"添加文件失败：\n{add_result.stderr}"
                    }
                })
                
                # 发送更新后的合并转发消息
                if isinstance(event, GroupMessageEvent):
                    await bot.call_api(
                        "send_group_forward_msg",
                        group_id=event.group_id,
                        messages=forward_msgs
                    )
                else:
                    await bot.call_api(
                        "send_private_forward_msg",
                        user_id=event.user_id,
                        messages=forward_msgs
                    )
                return
                
            # 提交变更
            commit_result = subprocess.run(
                ["git", "commit", "-m", "auto update"], 
                capture_output=True, 
                text=True
            )
            
            if commit_result.returncode != 0:
                forward_msgs.append({
                    "type": "node",
                    "data": {
                        "name": "EverSoul Git Error",
                        "uin": bot.self_id,
                        "content": f"提交变更失败：\n{commit_result.stderr}"
                    }
                })
                
                # 发送更新后的合并转发消息
                if isinstance(event, GroupMessageEvent):
                    await bot.call_api(
                        "send_group_forward_msg",
                        group_id=event.group_id,
                        messages=forward_msgs
                    )
                else:
                    await bot.call_api(
                        "send_private_forward_msg",
                        user_id=event.user_id,
                        messages=forward_msgs
                    )
                return
                
            # 推送到远程仓库
            push_result = subprocess.run(
                ["git", "push"], 
                capture_output=True, 
                text=True
            )
            
            if push_result.returncode != 0:
                forward_msgs.append({
                    "type": "node",
                    "data": {
                        "name": "EverSoul Git Error",
                        "uin": bot.self_id,
                        "content": f"推送变更失败：\n{push_result.stderr}"
                    }
                })
                
                # 发送更新后的合并转发消息
                if isinstance(event, GroupMessageEvent):
                    await bot.call_api(
                        "send_group_forward_msg",
                        group_id=event.group_id,
                        messages=forward_msgs
                    )
                else:
                    await bot.call_api(
                        "send_private_forward_msg",
                        user_id=event.user_id,
                        messages=forward_msgs
                    )
                return
                
            # 构建成功消息
            success_message = f"成功上传更新！\n共更新了 {changed_files_count} 个文件"
            success_message += "："
            for file in changed_files:
                success_message += f"\n- {file.strip()}"
            
            # 添加到合并转发消息
            forward_msgs.append({
                "type": "node",
                "data": {
                    "name": "EverSoul Git Update",
                    "uin": bot.self_id,
                    "content": success_message
                }
            })
            
            # 发送更新后的合并转发消息
            if isinstance(event, GroupMessageEvent):
                await bot.call_api(
                    "send_group_forward_msg",
                    group_id=event.group_id,
                    messages=forward_msgs
                )
            else:
                await bot.call_api(
                    "send_private_forward_msg",
                    user_id=event.user_id,
                    messages=forward_msgs
                )
        
            
        except Exception as e:
            logger.error(f"上传更新时发生错误: {e}")
            forward_msgs.append({
                "type": "node",
                "data": {
                    "name": "EverSoul Git Error",
                    "uin": bot.self_id,
                    "content": f"上传更新时发生错误: {str(e)}"
                }
            })
            
            # 发送更新后的合并转发消息
            if isinstance(event, GroupMessageEvent):
                await bot.call_api(
                    "send_group_forward_msg",
                    group_id=event.group_id,
                    messages=forward_msgs
                )
            else:
                await bot.call_api(
                    "send_private_forward_msg",
                    user_id=event.user_id,
                    messages=forward_msgs
                )
            
    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"检查更新时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
            )
            await bot.finish(f"检查更新时发生错误: {str(e)}")

@es_check_update.handle()
async def handle_es_check_update(event: GroupMessageEvent):
    group_id = event.group_id
    # 直接等待后台任务完成
    try:
        await check_update_background(group_id, event)
    except FinishedException:
        raise
    except Exception as e:
        import traceback
        error_location = traceback.extract_tb(e.__traceback__)[-1]
        logger.error(
            f"检查更新时发生错误:\n"
            f"错误类型: {type(e).__name__}\n"
            f"错误信息: {str(e)}\n"
            f"函数名称: {error_location.name}\n"
            f"问题代码: {error_location.line}\n"
        )
        await es_check_update.finish(f"检查更新时发生错误: {str(e)}")


# 初始化全局配置
current_data_source = load_data_source_config()

@es_switch_source.handle()
async def handle_switch_source(event: GroupMessageEvent):
    # 获取参数
    msg = str(event.get_message()).strip()
    args = msg.replace("es数据源切换", "").strip().lower()
    
    if not args:
        await es_switch_source.finish("请指定数据源类型：live 或 review")
    
    if args not in ["live", "review"]:
        await es_switch_source.finish("参数错误！请使用 'live' 或 'review'")
    
    # 更新全局配置
    global current_data_source
    current_data_source["type"] = args
    current_data_source["json_path"] = Path(f"/home/rikka/Eversoul/{args}_jsons")
    current_data_source["hero_alias_file"] = Path(__file__).parent / f"{args}_hero_aliases.yaml"
    
    # 保存配置到文件
    save_data_source_config(current_data_source)
    
    # 重新加载数据
    try:
        global alias_map, json_data
        alias_map = load_aliases()
        json_data = load_json_data()

    except Exception as e:
        if not isinstance(e, FinishedException):
            import traceback
            error_location = traceback.extract_tb(e.__traceback__)[-1]
            logger.error(
                f"切换数据源时发生错误:\n"
                f"错误类型: {type(e).__name__}\n"
                f"错误信息: {str(e)}\n"
                f"函数名称: {error_location.name}\n"
                f"问题代码: {error_location.line}\n"
                f"错误行号: {error_location.lineno}\n"
            )
            await es_switch_source.finish(f"切换数据源时发生错误: {str(e)}")
    
    await es_switch_source.finish(f"已切换到{args}数据源")