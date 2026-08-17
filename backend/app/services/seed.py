from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import hash_password
from backend.app.models.entities import Interest, User


INTERESTS = [
    # 运动健身
    ("综合运动", "🏅", "运动健身", 101), ("羽毛球", "🏸", "运动健身", 102),
    ("乒乓球", "🏓", "运动健身", 103), ("足球", "⚽", "运动健身", 104),
    ("篮球", "🏀", "运动健身", 105), ("排球", "🏐", "运动健身", 106),
    ("网球", "🎾", "运动健身", 107), ("跑步", "🏃", "运动健身", 108),
    ("游泳", "🏊", "运动健身", 109), ("健身", "🏋️", "运动健身", 110),
    ("瑜伽", "🧘", "运动健身", 111), ("滑板", "🛹", "运动健身", 112),
    # 音乐
    ("音乐综合", "🎧", "音乐", 201), ("华语流行", "🎤", "音乐", 202),
    ("古风音乐", "🏮", "音乐", 203), ("欧美音乐", "🌍", "音乐", 204),
    ("日系音乐", "🌸", "音乐", 205), ("K-Pop", "💿", "音乐", 206),
    ("摇滚", "🤘", "音乐", 207), ("民谣", "🪕", "音乐", 208),
    ("说唱", "🎙️", "音乐", 209), ("电子音乐", "🎛️", "音乐", 210),
    ("古典音乐", "🎻", "音乐", 211), ("乐器演奏", "🎼", "音乐", 212),
    ("吉他", "🎸", "音乐", 213), ("钢琴", "🎹", "音乐", 214),
    # 阅读
    ("阅读综合", "📚", "阅读", 301), ("人文历史", "🏛️", "阅读", 302),
    ("科幻小说", "🚀", "阅读", 303), ("推理悬疑", "🔍", "阅读", 304),
    ("文学名著", "📖", "阅读", 305), ("言情小说", "💌", "阅读", 306),
    ("社科心理", "🧠", "阅读", 307), ("网络文学", "📱", "阅读", 308),
    ("漫画绘本", "📔", "阅读", 309), ("诗歌", "🪶", "阅读", 310),
    # 游戏
    ("综合游戏", "🎮", "游戏", 401), ("MOBA", "⚔️", "游戏", 402),
    ("FPS", "🎯", "游戏", 403), ("二次元游戏", "✨", "游戏", 404),
    ("单机游戏", "🕹️", "游戏", 405), ("独立游戏", "👾", "游戏", 406),
    ("沙盒游戏", "🧱", "游戏", 407), ("模拟经营", "🏡", "游戏", 408),
    ("音乐游戏", "🎵", "游戏", 409), ("休闲手游", "📲", "游戏", 410),
    ("桌游", "🎲", "游戏", 411),
    # 动漫影视
    ("动漫综合", "🌸", "动漫影视", 501), ("电影综合", "🎬", "动漫影视", 502),
    ("国漫", "🐉", "动漫影视", 503), ("日漫", "🍥", "动漫影视", 504),
    ("美漫", "🦸", "动漫影视", 505), ("国产电影", "🎞️", "动漫影视", 506),
    ("欧美电影", "🍿", "动漫影视", 507), ("日韩电影", "🎥", "动漫影视", 508),
    ("科幻影视", "🛸", "动漫影视", 509), ("悬疑影视", "🕵️", "动漫影视", 510),
    ("喜剧", "😄", "动漫影视", 511), ("纪录片", "🌏", "动漫影视", 512),
    ("戏剧", "🎭", "动漫影视", 513),
    # 创作艺术
    ("摄影综合", "📷", "创作艺术", 601), ("人像摄影", "🧑‍🎨", "创作艺术", 602),
    ("风光摄影", "🌄", "创作艺术", 603), ("城市摄影", "🌆", "创作艺术", 604),
    ("纪实摄影", "📰", "创作艺术", 605), ("绘画", "🎨", "创作艺术", 606),
    ("舞蹈", "💃", "创作艺术", 607), ("书法", "🖌️", "创作艺术", 608),
    ("手工", "🧶", "创作艺术", 609), ("视频创作", "📹", "创作艺术", 610),
    ("写作", "✍️", "创作艺术", 611),
    # 户外旅行
    ("旅行综合", "🧳", "户外旅行", 701), ("国内旅行", "🗺️", "户外旅行", 702),
    ("境外旅行", "✈️", "户外旅行", 703), ("城市漫游", "🚶", "户外旅行", 704),
    ("徒步", "🥾", "户外旅行", 705), ("登山", "⛰️", "户外旅行", 706),
    ("露营", "⛺", "户外旅行", 707), ("骑行", "🚲", "户外旅行", 708),
    # 生活方式
    ("美食探店", "🍜", "生活方式", 801), ("烘焙", "🧁", "生活方式", 802),
    ("咖啡", "☕", "生活方式", 803), ("茶饮", "🍵", "生活方式", 804),
    ("猫咪", "🐱", "生活方式", 805), ("狗狗", "🐶", "生活方式", 806),
    ("宠物", "🐾", "生活方式", 807), ("花艺", "💐", "生活方式", 808),
    ("穿搭", "👗", "生活方式", 809), ("手账", "📒", "生活方式", 810),
    # 科技校园
    ("编程", "💻", "科技校园", 901), ("AI", "🤖", "科技校园", 902),
    ("数码科技", "⌚", "科技校园", 903), ("学术科研", "🔬", "科技校园", 904),
    ("辩论", "🗣️", "科技校园", 905), ("志愿服务", "🤝", "科技校园", 906),
    ("创业", "💡", "科技校园", 907), ("语言学习", "🗺️", "科技校园", 908),
]


DEMO_USERS = [
    ("20260001", "13800000001", "linxia@example.com", "林夏", "female", date(2005, 5, 18), "计算机学院", "2023级", "周末会带相机去操场散步，也在学尤克里里。", ["人像摄影", "华语流行", "城市漫游", "猫咪", "编程"]),
    ("20260002", "13800000002", "sugar@example.com", "小糖", "female", date(2004, 11, 2), "外国语学院", "2022级", "电影散场后还愿意聊半小时的人，请出现。", ["悬疑影视", "推理悬疑", "烘焙", "志愿服务"]),
    ("20260003", "13800000003", "momo@example.com", "沫沫", "female", date(2005, 8, 29), "艺术学院", "2023级", "画画、跳舞，也收藏落日。", ["绘画", "舞蹈", "风光摄影", "戏剧"]),
    ("20260004", "13800000004", "yuzhou@example.com", "予舟", "female", date(2003, 12, 16), "新闻学院", "2022级", "校报记者，正在把好奇心写进每一天。", ["人文历史", "辩论", "国内旅行", "志愿服务", "纪实摄影"]),
    ("20260005", "13800000005", "mint@example.com", "薄荷", "female", date(2004, 6, 8), "生命科学学院", "2022级", "喜欢小动物和一切毛茸茸。", ["猫咪", "狗狗", "露营", "手工", "美食探店"]),
    ("20260006", "13800000006", "jiangyu@example.com", "江屿", "male", date(2004, 7, 21), "计算机学院", "2022级", "白天写代码，晚上打羽毛球，偶尔弹吉他。", ["编程", "羽毛球", "华语流行", "吉他", "MOBA"]),
    ("20260007", "13800000007", "nanfeng@example.com", "南风", "male", date(2005, 3, 10), "建筑学院", "2023级", "喜欢观察城市，也喜欢没有目的地的骑行。", ["城市摄影", "绘画", "骑行", "城市漫游"]),
    ("20260008", "13800000008", "xinghe@example.com", "星河", "male", date(2003, 9, 5), "经济学院", "2021级", "桌游组局常驻发起人，认真听每一种观点。", ["桌游", "辩论", "欧美电影", "人文历史"]),
    ("20260009", "13800000009", "azhe@example.com", "阿哲", "male", date(2004, 1, 27), "体育学院", "2022级", "篮球、健身、露营，行动派但不催人。", ["篮球", "健身", "露营", "狗狗"]),
    ("20260010", "13800000010", "qimu@example.com", "栖木", "male", date(2005, 10, 12), "音乐学院", "2023级", "乐队键盘手，最近在学烘焙。", ["日系音乐", "钢琴", "烘焙", "日漫", "国内旅行"]),
]

DEMO_LOCATIONS = {
    "20260001": ("陕西", "西安"),
    "20260002": ("陕西", "咸阳"),
    "20260003": ("四川", "成都"),
    "20260004": ("陕西", "西安"),
    "20260005": ("河南", "郑州"),
    "20260006": ("陕西", "西安"),
    "20260007": ("陕西", "咸阳"),
    "20260008": ("四川", "成都"),
    "20260009": ("陕西", "宝鸡"),
    "20260010": ("河南", "郑州"),
}

DEMO_HOMETOWNS = {
    "20260001": ("陕西", "西安"),
    "20260002": ("河南", "洛阳"),
    "20260003": ("四川", "成都"),
    "20260004": ("山东", "济南"),
    "20260005": ("河南", "郑州"),
    "20260006": ("陕西", "宝鸡"),
    "20260007": ("陕西", "西安"),
    "20260008": ("四川", "绵阳"),
    "20260009": ("陕西", "咸阳"),
    "20260010": ("河南", "洛阳"),
}

DEMO_BODY_METRICS = {
    "20260001": (165, 51.0),
    "20260002": (162, 49.5),
    "20260003": (168, 52.0),
    "20260004": (166, 53.0),
    "20260005": (160, 48.0),
    "20260006": (178, 68.0),
    "20260007": (181, 70.0),
    "20260008": (175, 66.0),
    "20260009": (183, 76.0),
    "20260010": (176, 64.0),
}

DEMO_SCHOOL = "CampusMatch示范大学"


async def seed_database(db: AsyncSession, *, include_demo_users: bool = True) -> None:
    existing_interests = {item.name: item for item in (await db.scalars(select(Interest))).all()}
    for name, emoji, category, sort_order in INTERESTS:
        interest = existing_interests.get(name)
        if interest:
            interest.emoji = emoji
            interest.category = category
            interest.sort_order = sort_order
        else:
            interest = Interest(name=name, emoji=emoji, category=category, sort_order=sort_order)
            db.add(interest)
            existing_interests[name] = interest
    await db.flush()

    if not include_demo_users:
        await db.commit()
        return

    user_count = await db.scalar(select(func.count(User.id)))
    if user_count:
        demo_accounts = [item[0] for item in DEMO_USERS]
        users = (await db.scalars(select(User).where(User.account.in_(demo_accounts)))).all()
        for user in users:
            if not user.school:
                user.school = DEMO_SCHOOL
            if not user.avatar_url:
                user.avatar_url = f"/static/demo-{'male' if user.gender == 'male' else 'female'}.svg"
            province, city = DEMO_LOCATIONS[user.account]
            hometown_province, hometown_city = DEMO_HOMETOWNS[user.account]
            height_cm, weight_kg = DEMO_BODY_METRICS[user.account]
            if not user.location_province:
                user.location_province = province
            if not user.location_city:
                user.location_city = city
            if not user.hometown_province:
                user.hometown_province = hometown_province
            if not user.hometown_city:
                user.hometown_city = hometown_city
            if user.height_cm is None:
                user.height_cm = height_cm
            if user.weight_kg is None:
                user.weight_kg = weight_kg
        await db.commit()
        return

    interests = {item.name: item for item in (await db.scalars(select(Interest))).all()}
    password_hash = hash_password("Campus123")
    for account, phone, email, nickname, gender, birth_date, department, grade, bio, tags in DEMO_USERS:
        province, city = DEMO_LOCATIONS[account]
        hometown_province, hometown_city = DEMO_HOMETOWNS[account]
        height_cm, weight_kg = DEMO_BODY_METRICS[account]
        user = User(
            account=account,
            phone=phone,
            email=email,
            password_hash=password_hash,
            nickname=nickname,
            gender=gender,
            birth_date=birth_date,
            school=DEMO_SCHOOL,
            department=department,
            grade=grade,
            location_province=province,
            location_city=city,
            hometown_province=hometown_province,
            hometown_city=hometown_city,
            height_cm=height_cm,
            weight_kg=weight_kg,
            avatar_url=f"/static/demo-{'male' if gender == 'male' else 'female'}.svg",
            bio=bio,
            interests=[interests[tag] for tag in tags],
            is_superuser=account == "20260006",
        )
        db.add(user)
    await db.commit()
