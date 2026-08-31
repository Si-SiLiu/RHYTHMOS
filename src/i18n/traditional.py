"""Small, dependency-free Simplified-to-Traditional display conversion.

The application keeps Simplified Chinese literals in a few page-local
``_ui`` helpers for the ``zh-CN``/English path.  Traditional Chinese must not
reuse those literals verbatim.  This module covers the characters used by the
first-party pages without adding a runtime OpenCC dependency; locale resources
remain the source of truth whenever a translation key exists.
"""


# Common UI characters.  Keep this table intentionally local and deterministic
# so the macOS bundle does not need a network package or an extra native
# library just to render zh-TW.
_CHARACTER_PAIRS = (
    "与與 专專 两兩 严嚴 个個 为為 举舉 义義 习習 于於 亚亞 仅僅 从從 优優 会會 传傳 体體 余餘 侧側 关關 养養 内內 写寫 况況 准準 减減 击擊 划劃 则則 别別 剂劑 务務 动動 劳勞 势勢 匀勻 区區 医醫 协協 单單 卧臥 历歷 双雙 发發 变變 台臺 号號 后後 响響 哑啞 围圍 图圖 处處 备備 复復 头頭 学學 实實 宽寬 对對 将將 层層 属屬 带帶 并並 库庫 应應 开開 异異 张張 弯彎 弹彈 当當 录錄 径徑 忆憶 态態 总總 悬懸 惯慣 愿願 户戶 执執 扫掃 扰擾 抛拋 择擇 换換 据據 摄攝 撑撐 数數 断斷 无無 时時 显顯 暂暫 机機 杂雜 条條 来來 极極 构構 枢樞 标標 样樣 档檔 检檢 欧歐 没沒 测測 浏瀏 滚滾 灵靈 点點 热熱 状狀 独獨 环環 现現 电電 疗療 盘盤 确確 离離 积積 称稱 稳穩 签籤 简簡 类類 纤纖 约約 级級 纳納 纵縱 线線 练練 经經 绑綁 结結 统統 继繼 绩績 续續 绳繩 维維 综綜 罗羅 群羣 联聯 脑腦 节節 范範 荐薦 药藥 获獲 营營 虫蟲 补補 装裝 见見 观觀 规規 视視 览覽 觉覺 触觸 计計 认認 训訓 议議 记記 设設 评評 识識 诊診 试試 该該 详詳 误誤 请請 读讀 负負 败敗 质質 趋趨 转轉 轮輪 轻輕 载載 较較 辅輔 输輸 过過 运運 还還 这這 进進 连連 迟遲 适適 选選 遗遺 释釋 针針 钝鈍 钟鐘 钠鈉 钮鈕 铃鈴 错錯 键鍵 长長 问問 间間 阶階 际際 险險 难難 静靜 页頁 项項 预預 颈頸 频頻 题題 风風 飞飛 饮飲 馈饋 马馬 验驗 髋髖 鲁魯 鸟鳥 麦麥 齐齊"
).split()
_CHARACTER_MAP = {pair[0]: pair[1] for pair in _CHARACTER_PAIRS if len(pair) == 2}

# Character conversion cannot decide every polysemantic character.  These
# phrases are common in the page-local copy and need Taiwan-standard forms.
_PHRASE_MAP = {
    "干扰": "干擾",
    "干扰抑制": "干擾抑制",
    "个人": "個人",
    "历史": "歷史",
    "训练": "訓練",
    "建议": "建議",
    "基线": "基線",
    "分钟": "分鐘",
    "周一": "週一",
    "周二": "週二",
    "周三": "週三",
    "周四": "週四",
    "周五": "週五",
    "周六": "週六",
    "周日": "週日",
}


def traditionalize(value: object) -> object:
    """Convert display text to Traditional Chinese while preserving types."""
    if not isinstance(value, str):
        return value
    converted = value
    for source, target in _PHRASE_MAP.items():
        converted = converted.replace(source, target)
    return converted.translate(str.maketrans(_CHARACTER_MAP))
