const THEMES = [
  {
    id: "family",
    label: "人物与陪伴",
    tags: ["people", "children", "baby", "family", "couple", "friends", "selfie", "group photo", "portrait", "人物", "儿童", "婴儿", "家庭", "情侣", "朋友", "自拍", "合影"],
    titles: [
      ["熟悉的人，", "又回到画面里。"],
      ["有些陪伴，", "一出现就认得。"],
      ["这一轮先遇见的，", "是照片里的人。"],
    ],
    sentence: "这组照片更接近人物、陪伴和共同经历。",
  },
  {
    id: "celebration",
    label: "相聚与纪念",
    tags: ["party", "wedding", "birthday", "festival", "christmas", "graduation", "concert", "聚会", "婚礼", "生日", "节日", "圣诞", "春节", "毕业", "演唱会"],
    titles: [
      ["热闹散场以后，", "照片还记得当时。"],
      ["值得纪念的日子，", "又被翻到了。"],
      ["那些相聚的时刻，", "正在重新亮起来。"],
    ],
    sentence: "这一组带着相聚、庆祝或纪念日的气息。",
  },
  {
    id: "coast",
    label: "天空与远方",
    tags: ["sunset", "sunrise", "beach", "lake", "river", "sky", "clouds", "boat", "日落", "日出", "海滩", "湖泊", "河流", "天空", "云", "船"],
    titles: [
      ["光落在远处，", "这一刻又近了。"],
      ["天空、风和水面，", "把时间慢了下来。"],
      ["这一轮回忆，", "先从远处的光开始。"],
    ],
    sentence: "这组照片更接近天空、水面与开阔的远方。",
  },
  {
    id: "nature",
    label: "自然与风景",
    tags: ["mountain", "forest", "snow", "rain", "flowers", "grass", "desert", "park", "landscape", "山脉", "森林", "雪", "雨", "花", "草地", "沙漠", "公园", "风景照"],
    titles: [
      ["走过的风景，", "没有真的走远。"],
      ["山野和光线，", "替那天保留了位置。"],
      ["这一轮先回到，", "那些安静的风景里。"],
    ],
    sentence: "这一组由自然、风景和户外光线串在一起。",
  },
  {
    id: "city",
    label: "城市与夜色",
    tags: ["city", "architecture", "street", "night", "train", "car", "office", "城市", "建筑", "街道", "夜景", "火车", "汽车", "办公室"],
    titles: [
      ["街灯亮起来时，", "城市换了一种表情。"],
      ["走过的街道，", "还留着那天的光。"],
      ["这一轮回忆，", "从城市的夜色开始。"],
    ],
    sentence: "这组照片更接近街道、建筑与城市里的光。",
  },
  {
    id: "food",
    label: "味道与日常",
    tags: ["food", "cake", "coffee", "restaurant", "kitchen", "食物", "蛋糕", "咖啡", "餐厅", "厨房"],
    titles: [
      ["有些日子，", "是从味道想起来的。"],
      ["一餐一杯之间，", "日常也值得留下。"],
      ["这一轮翻到的，", "是生活里的好味道。"],
    ],
    sentence: "这一组由餐桌、咖啡和生活里的味道连在一起。",
  },
  {
    id: "pets",
    label: "动物与陪伴",
    tags: ["pet", "cat", "dog", "bird", "fish", "animal", "wildlife", "宠物", "猫", "狗", "鸟", "鱼", "动物", "野生动物"],
    titles: [
      ["镜头里的小家伙，", "又跑回来了。"],
      ["不会说话的陪伴，", "照片一直替你记着。"],
      ["这一轮先遇见的，", "是熟悉的小动物。"],
    ],
    sentence: "这组照片更接近动物和那些安静的陪伴。",
  },
  {
    id: "motion",
    label: "运动与出发",
    tags: ["travel", "airplane", "bicycle", "sports", "running", "swimming", "basketball", "football", "yoga", "旅行", "飞机", "自行车", "运动", "跑步", "游泳", "篮球", "足球", "瑜伽"],
    titles: [
      ["身体在路上时，", "时间也有了方向。"],
      ["出发和抵达之间，", "这些瞬间被留下了。"],
      ["这一轮回忆，", "带着一点正在发生的风。"],
    ],
    sentence: "这一组带着旅行、运动或正在出发的节奏。",
  },
  {
    id: "private",
    label: "私人收藏",
    tags: ["nsfw", "nude", "explicit", "nipples", "female genitals", "vulva", "labia", "lingerie", "gravure", "model portrait", "photobook"],
    titles: [
      ["这组私人影像，", "重新回到眼前。"],
      ["只属于你的收藏，", "这次排在了前面。"],
      ["这一轮翻到的，", "是更私人的一组画面。"],
    ],
    sentence: "这一组来自更私人的影像收藏。",
  },
];

const FALLBACK_TITLES = [
  ["刚刚浮上来的照片，", "组成了这一轮相遇。"],
  ["每次重新抽取，", "都会换一个回去的入口。"],
  ["这一轮的前三张，", "正在把时间接回来。"],
];

function shortLabel(value, maxLength = 16) {
  const text = (value || "").trim();
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function sourceName(photo) {
  const parts = (photo.folder || "").split(" / ").filter(Boolean);
  return shortLabel(parts.at(-1) || "未命名来源");
}

function chineseDate(rawDate, short = false) {
  const match = String(rawDate || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return "日期未知";
  const [, year, month, day] = match;
  return short
    ? `${Number(month)}月${Number(day)}日`
    : `${Number(year)}年${Number(month)}月${Number(day)}日`;
}

function selectTheme(photos) {
  const tags = photos.flatMap((photo) => photo.tags || []).map((tag) => String(tag).trim().toLowerCase());
  let best = null;
  let bestScore = 0;
  for (const theme of THEMES) {
    const score = theme.tags.reduce((total, tag) => total + tags.filter((value) => value === tag).length, 0);
    if (score > bestScore) {
      best = theme;
      bestScore = score;
    }
  }
  return bestScore > 0 ? best : null;
}

function stableVariant(photos, length) {
  const seed = photos.reduce((total, photo) => total + Number(photo.id || 0), 0);
  return Math.abs(seed) % length;
}

export function buildHeroCopy(photos, total) {
  const dates = [...new Set(photos.map((photo) => String(photo.date || "").slice(0, 10)).filter(Boolean))].sort();
  const sources = [...new Set(photos.map(sourceName))];
  const dateRange = dates.length > 1
    ? `${chineseDate(dates[0], true)} — ${chineseDate(dates.at(-1), true)}`
    : chineseDate(dates[0]);
  const theme = selectTheme(photos);
  const titles = theme?.titles || FALLBACK_TITLES;
  const title = titles[stableVariant(photos, titles.length)];
  const sourceText = sources.slice(0, 3).join("、") || "当前来源";
  const themeSentence = theme?.sentence || `这组照片来自 ${sourceText}，时间落在 ${dateRange}。`;

  return {
    eyebrow: `${theme?.label || "当前瀑布流"} · ${dateRange}`,
    title,
    description: `${themeSentence} 右边就是瀑布流最前面的 ${photos.length} 张：按住可以拖动，双击进入时间线。图库中共有 ${new Intl.NumberFormat("zh-CN").format(total || 0)} 张照片。`,
  };
}
