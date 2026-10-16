# React 组件与状态

组件描述界面，props 传递数据，state 保存组件内部状态。

## 状态更新

```tsx
const [count, setCount] = useState(0);
setCount((current) => current + 1);
```

更新依赖旧值时使用函数式更新。不要直接修改已有数组或对象。
