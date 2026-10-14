"""确定性数据集生成器：以 openKylin 桌面用户为场景，构造多会话对话与记忆考题。"""
import random
from typing import List

from .schema import Case, Turn, ABSTAIN

# 属性 -> 候选值。场景贴合 openKylin 用户的日常使用。
ATTRS = {
    "默认桌面环境": ["UKUI", "KDE Plasma", "GNOME", "Xfce"],
    "常用编辑器": ["VS Code", "Vim", "Kate", "Emacs", "Neovim"],
    "默认终端": ["mate-terminal", "Konsole", "Alacritty", "kitty"],
    "常用输入法": ["搜狗输入法", "Rime 中州韵", "fcitx5 拼音", "讯飞输入法"],
    "主力开发语言": ["Python", "Rust", "Go", "C++", "Java"],
    "工作目录": ["~/work", "~/code", "/data/projects", "~/dev"],
    "显卡型号": ["RTX 4060", "Arc A770", "RX 7800", "摩尔线程 S80"],
    "CPU 架构": ["x86_64", "aarch64", "riscv64", "loongarch64"],
    "常用浏览器": ["Firefox", "Chromium", "奇安信浏览器", "360 安全浏览器"],
    "系统版本": ["openKylin 2.0", "openKylin 2.0 SP1", "openKylin 1.0.2"],
    "所在城市": ["上海", "北京", "深圳", "成都", "长沙"],
    "包管理偏好": ["apt", "flatpak", "源码编译", "kare"],
}

FILLERS = [
    "帮我看看 apt update 报错是什么意思。",
    "今天系统更新后风扇有点吵。",
    "怎么在 UKUI 里设置快捷键？",
    "推荐几个好用的截图工具吧。",
    "我想把 home 目录挂载到另一块硬盘。",
    "ls -la 的输出怎么理解？",
    "帮我写个 shell 脚本批量重命名图片。",
    "wifi 偶尔会断，怎么排查？",
    "systemctl 和 service 有什么区别？",
    "麒麟软件商店里能装微信吗？",
    "解释一下 cgroup 是做什么的。",
    "怎么查看当前内核版本？",
]
ASSISTANT_ACK = "好的，我记下了。"


def state(attr, value):
    return f"我的{attr}是{value}。"


def change(attr, value):
    return f"更正一下，我的{attr}现在改成{value}了。"


DISTRACTORS = [
    "我的同事说他的{a}是{v}。",
    "我的室友的{a}是{v}。",
    "我的笔记本上一个系统的{a}是{v}。",
    "我在考虑要不要把{a}换成{v}，还没决定。",
    "帮我比较一下{a}选{v}的优缺点。",
]


def distract(rng, attr):
    return rng.choice(DISTRACTORS).format(a=attr, v=rng.choice(ATTRS[attr]))


def forget(attr):
    return f"请忘掉我的{attr}，不要再记住它。"


class _Builder:
    def __init__(self, rng, n_sessions, turns_per_session, n_distract):
        self.rng = rng
        self.n_sessions = n_sessions
        self.tps = turns_per_session
        # 每个会话预先填满闲聊，事件之后插入到指定会话
        self.slots = [[] for _ in range(n_sessions)]
        self.n_distract = n_distract

    def noise(self, *attrs):
        """为相关属性注入同主题干扰句，考验检索的精确性。"""
        for a in attrs:
            for _ in range(self.n_distract):
                self.put(self.rng.randrange(self.n_sessions), distract(self.rng, a))

    def put(self, session, text):
        self.slots[session].append(text)
        return self

    def build(self):
        sessions = []
        for s, events in enumerate(self.slots):
            n_fill = max(self.tps - len(events), 0)
            fillers = iter(self.rng.sample(FILLERS * 3, n_fill))
            total = len(events) + n_fill
            # 事件保持相对顺序，随机散布在闲聊之间
            positions = set(self.rng.sample(range(total), len(events)))
            ev = iter(events)
            mixed = [next(ev) if i in positions else next(fillers) for i in range(total)]
            turns = []
            for i, text in enumerate(mixed):
                turns.append(Turn(s, 2 * i, "user", text))
                turns.append(Turn(s, 2 * i + 1, "assistant", ASSISTANT_ACK))
            sessions.append(turns)
        return sessions


def generate(n_per_category=20, n_sessions=6, turns_per_session=8, seed=42, n_distract=3) -> List[Case]:
    rng = random.Random(seed)
    cases = []
    attrs = list(ATTRS)

    def new():
        return _Builder(rng, n_sessions, turns_per_session, n_distract)

    for k in range(n_per_category):
        # recall：首个会话陈述，最后提问
        a = rng.choice(attrs); v = rng.choice(ATTRS[a])
        b = new(); b.put(0, state(a, v)); b.noise(a)
        cases.append(Case(f"recall-{k}", "recall", b.build(), f"我的{a}是什么？", [v]))

        # update：先陈述，后续会话修改（可能多次）
        a = rng.choice(attrs); vals = rng.sample(ATTRS[a], min(3, len(ATTRS[a])))
        b = new(); b.put(0, state(a, vals[0]))
        b.put(rng.randrange(1, n_sessions), change(a, vals[1])); b.noise(a)
        cases.append(Case(f"update-{k}", "update", b.build(), f"我的{a}是什么？", [vals[1]], [vals[0]]))

        # multi：两条事实分散在不同会话
        a1, a2 = rng.sample(attrs, 2)
        v1, v2 = rng.choice(ATTRS[a1]), rng.choice(ATTRS[a2])
        b = new(); b.put(0, state(a1, v1)); b.put(rng.randrange(1, n_sessions), state(a2, v2)); b.noise(a1, a2)
        cases.append(Case(f"multi-{k}", "multi", b.build(), f"我的{a1}和{a2}分别是什么？", [v1, v2]))

        # temporal：问最初的值
        a = rng.choice(attrs); vals = rng.sample(ATTRS[a], 2)
        b = new(); b.put(0, state(a, vals[0])); b.put(rng.randrange(1, n_sessions), change(a, vals[1])); b.noise(a)
        cases.append(Case(f"temporal-{k}", "temporal", b.build(), f"我最初说的{a}是什么？", [vals[0]]))

        # forget：陈述后要求遗忘
        a = rng.choice(attrs); v = rng.choice(ATTRS[a])
        b = new(); b.put(0, state(a, v)); b.put(rng.randrange(1, n_sessions), forget(a)); b.noise(a)
        cases.append(Case(f"forget-{k}", "forget", b.build(), f"我的{a}是什么？", [ABSTAIN], [v]))

        # abstain：问从未提过的属性（但对话里有其他事实做干扰）
        a, other = rng.sample(attrs, 2)
        b = new(); b.put(0, state(other, rng.choice(ATTRS[other]))); b.noise(a)
        cases.append(Case(f"abstain-{k}", "abstain", b.build(), f"我的{a}是什么？", [ABSTAIN]))

    return cases
