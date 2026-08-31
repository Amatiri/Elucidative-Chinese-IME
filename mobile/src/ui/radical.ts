/**
 * 形部表（部首表）—— 对齐 ime.py:984-1011 的 radical_table_data。
 *
 * 26 组：25 个声母字母（a–z 去掉 e）+「0-9」。注意计划 stellar-vortex-babbage.md
 * 正文误写为「25 组 / 24 个字母」，以 ime.py 运行时数据源为准（实际 26 组）。
 * 手机端做成覆盖键盘的浮层（上滑 Z 触发），作为编码学习辅助。数据只读，
 * 渲染时原样展示，移动端不修改。
 *
 * 移植时严格保持原串（0-9 组的「复」收尾），不重排、不补全——它与桌面端
 * 行为必须零分歧。首组标签桌面端为「a(副)」，移动端用户定稿为「笔画」
 * （该组内容丶一丨丿乙乛𠃌乚𡿨 全为笔画），仅显示标签不同，部首串未动。
 */

export interface RadicalGroup {
  /** 键标签，如 "笔画" / "b" / "0-9" */
  label: string;
  /** 该组下的部首串 */
  chars: string;
}

export const RADICAL_TABLE: readonly RadicalGroup[] = [
  { label: "笔画", chars: "丶一丨丿乙乛𠃌乚𡿨" },
  { label: "b", chars: "宀阝冫贝疒白卜八匕癶" },
  { label: "c", chars: "车艹厂凵寸卄屮" },
  { label: "d", chars: "刀歹大亠冖丷斗豆" },
  { label: "f", chars: "风方父缶臼辰非" },
  { label: "g", chars: "工广弓光囗革戈瓜艮谷骨" },
  { label: "h", chars: "火户禾⺌羊虍黑" },
  { label: "i", chars: "虫页雨弋彐彑臣赤𡗗尺" },
  { label: "j", chars: "金巾廴冂几𠘨卩己见斤皀" },
  { label: "k", chars: "口又舌用角" },
  { label: "l", chars: "娄云勹力龙老卤里卵" },
  { label: "m", chars: "木彡釆马门皿毛目矛米麦" },
  { label: "n", chars: "女牛鸟耒齿" },
  { label: "o", chars: "耳匚二儿㔾" },
  { label: "p", chars: "攴片殳丬皮髟㐅" },
  { label: "q", chars: "气犬豸欠青" },
  { label: "r", chars: "人肉入日リ" },
  { label: "s", chars: "示丝石尸十厶巳" },
  { label: "t", chars: "土彳幺夕田" },
  { label: "u", chars: "攵水矢手食山士豕身" },
  { label: "v", chars: "乑争舟止爪鬼支" },
  { label: "w", chars: "王网瓦韦隹文" },
  { label: "x", chars: "穴𰃮心西小巛血辛习" },
  { label: "y", chars: "言酉月鱼衣尢聿业羽黾音" },
  { label: "z", chars: "辶竹足子自走" },
  { label: "0-9", chars: "口丨一八㐅中大厂乙复" },
];
