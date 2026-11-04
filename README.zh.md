# dsh-logo-golden

DeepSeek Harness 侧栏品牌组合的抛光黄金版本 —— 鲸鱼图标、`deepseek` 字标与 HARNESS
铭牌，全部用原始矢量绘制，并有一道斜向金属光带每三秒完整掠过整个组合。

![光带掠过品牌组合](docs/sweep-strip.png)

本仓库是插件 `@linxin666/dsh-client-ui-brand-gold` 的独立分发版：完整源码、测试与构建
所需预设都在这里，新克隆下 `pnpm install && pnpm build` 即可工作，不依赖其它检出。

## 它做了什么

- **黄金品牌。** 鲸鱼轮廓、每一个字标笔画与 HARNESS 铭牌都沿用原始路径；材质分层绘制在
  轮廓内部：主光在左上的暖金渐变、右下的反光、接触阴影、柔光箱反射与内嵌倒角。没有任何
  一层撑大轮廓，每层都裁剪到原始几何，HARNESS 深色铭文保持深色。
- **是扫光，不是整体闪光。** 一道相对竖直倾斜 25 度的斜向光带同时穿过整个组合，宽金亮带
  为 0.55 倍组合宽度，中间是窄香槟光芯；局部形变（1.08 倍放大、0.8 px 上浮）与光带移动
  的是同一份材质，静止时精确回到恒等映射。
- **每一块金属都受光，包括暗金。** 由原始矢量光栅出的几何遮罩决定“是不是金属”：鲸鱼填充
  区、每个实心笔画与铭牌受光；铭牌深色铭文、镂空、字符之间的空隙与背景永不受光。亮度 8%
  的暗金笔画受光，同样亮度的深色铭文不受光。
- **三秒节奏。** 每 3000 ms 开始一轮：入场 250 ms、遍历金属 2200 ms、退场 250 ms、静止
  300 ms。开始时刻落在绝对栅格上，掉帧不会累积漂移，错过的周期直接跳过而不补播。
- **扩展动态范围，如实报告。** 画布请求 `rgba16float` 与 `toneMapping: 'extended'`，
  在透明背景下以显示参考白为基准瞄准光芯 1600 nit 短时峰值。离屏读回只能证明**着色器**
  输出了超过 1.0 的值；诊断不会把推算值说成屏幕实测。
- **回退后仍是同一个品牌。** 没有 WebGPU、没有 popover API，或处于
  `prefers-reduced-motion: reduce` 时，保留静态黄金组合：同样的矢量、同样的几何、没有动画。

## 安装

插件以 Cordis bundle 行的形式挂载。在 DSH profile 中：

```sh
dsh plugin --profile desktop add @linxin666/dsh-client-ui-brand-gold
```

或手工在 profile 的 `cordis.patch.yml` 中加入：

```yaml
- insert:
    - id: ui-brand-gold
      name: "@linxin666/dsh-client-ui-brand-gold"
```

行 id 不得与官方行冲突（loader 对同一 id 只保留一个且不报错），`name` 必须与包名完全
一致：client 模块加载器只把浏览器半区挂到说明符等于包名的那一行上。

## 构建与测试

```sh
pnpm install
pnpm test        # 112 个单元测试
pnpm typecheck
pnpm build       # tsdown 打捆 + tsc 生成声明到 lib/
```

`build/tsdown.client.ts` 是共享的客户端打捆预设，为让仓库独立可构建而内置；它与 dsh-web
monorepo 中所有插件用的是同一份文件。

## 扫光是怎么工作的

```
sweep.ts       ← 全部参数：周期、阶段、宽度、增益、峰值
trajectory.ts  ← 过四个阶段边界的一条单调曲线
timeline.ts    ← 绝对周期栅格、一个定时器、一个动画循环
layout.ts      ← 渲染盒 → 同一块画布；整条光带的行程
beam.ts        ← 光分布：FWHM、倾角、有限支撑、形变
geometry-mask.ts ← 原始矢量 → 哪些像素是金属
surface.ts     ← 资格（遮罩）与着色（亮度、反照率下限）分开
raster.ts      ← 实时 SVG，内联计算后的绘制属性
material.ts    ← 着色器采样的合成材质
renderer.ts    ← WebGPU：遮罩、逆向形变、配光、扩展输出
overlay.ts     ← 拥有以上全部资源的控制器
```

动画依赖的每个数字都是 `src/client/sweep.ts` 里的参数；着色器逐项复刻 CPU 侧的算术，
测试断言的是**最终交付**的结果（亮带宽度、光芯宽度、峰值亮度、哪些像素真的亮了），
而不是输入参数本身。

## 包结构

| 路径 | 内容 |
|---|---|
| `src/index.ts` | host 半区：注册 bundle，不含行为 |
| `src/client/` | 浏览器半区：组件、控制器、着色器 |
| `tests/` | vitest 测试，涉及 DOM 的用 jsdom |
| `build/` | 内置的客户端打捆预设 |
| `locale/` | 插件列表元数据（en / zh） |
| `cordis.patch.yml` | bundle 行 |

## 许可

Apache-2.0，见 [LICENSE](LICENSE)。
