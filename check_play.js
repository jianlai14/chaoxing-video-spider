/* 播放自检：点一次播放按钮，如实报告视频有没有真的在播
 *
 * 用法（Edge）：
 *   在章节页（studentstudy）按 F12 打开开发人员工具 -> 控制台(Console)
 *   -> 整段粘贴回车。脚本会自动钻进各层 iframe 找播放器。
 *   首次粘贴若被拦，在输入框手打「允许粘贴」回车后再粘。
 *
 * 它只做三件事：定位按钮 -> 点一次 -> 观察 4 秒读状态。
 * 不改进度、不改上报、不循环。
 */
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ok = (b) => (b ? '是' : '否');

  // 1) 递归找 .vjs-big-play-button（视频在 insertvideo iframe 里）
  function find(win = window, depth = 0, out = []) {
    try {
      const btn = win.document.querySelector('.vjs-big-play-button');
      if (btn) out.push({ win, depth, btn });
      for (const f of win.document.querySelectorAll('iframe,frame')) {
        try {
          if (f.contentWindow && f.contentWindow.document) find(f.contentWindow, depth + 1, out);
        } catch (e) { /* 跨域跳过 */ }
      }
    } catch (e) { /* 同上 */ }
    return out;
  }

  const hits = find();
  if (!hits.length) {
    console.warn('[自检] 没找到播放按钮。确认已打开某个视频小节，且 iframe 已加载完。');
    return;
  }

  // 多层都命中时优先取可见的那个
  const visible = hits.filter((h) => getComputedStyle(h.btn).display !== 'none');
  const { win, depth, btn } = visible[0] || hits[0];
  const box = btn.closest('.video-js');
  const video = box && box.querySelector('video');
  const player = win.videojs ? win.videojs.getPlayer(box) : null;

  console.log('%c[自检] 定位结果', 'font-weight:bold');
  console.table([{
    所在层: depth,
    播放器容器: box ? (box.id || '(无 id)') : '未找到',
    videojs对象: ok(!!win.videojs),
    player实例: ok(!!player),
    video元素: ok(!!video),
    按钮可见: box ? ok(getComputedStyle(btn).display !== 'none') : '-',
    当前时长: player && player.duration() ? player.duration().toFixed(1) + 's' : '未知',
    当前状态: player ? (player.paused() ? '暂停' : '播放中') : '-'
  }]);

  if (!video) {
    console.warn('[自检] 容器里没有 <video>，播放器可能还没初始化完成，等几秒再试。');
    return;
  }

  const state = () => ({
    paused: video.paused,
    time: +video.currentTime.toFixed(2),
    readyState: video.readyState,
    muted: video.muted,
    error: video.error ? video.error.code + ' ' + (video.error.message || '') : '无'
  });

  // 2) 点一次按钮，观察 2 秒
  const before = state();
  btn.click();
  await sleep(2000);
  let after = state();
  console.log('[自检] 首次点击后', { 之前: before, 之后: after });

  // 3) 仍在暂停 => 多半是浏览器自动播放策略拦截，静音后重试一次
  let needMute = false;
  if (after.paused) {
    needMute = true;
    if (player) player.muted(true); else video.muted = true;
    btn.click();
    await sleep(2000);
    after = state();
    console.log('[自检] 静音重试后', after);
  }

  // 4) 再等 2 秒，确认时间轴真的在走（排除"已解除暂停但卡住"）
  const t1 = state().time;
  await sleep(2000);
  const t2 = state().time;
  const advancing = t2 - t1 > 0.5;

  // 5) 结论
  const verdict = advancing
    ? (needMute ? '可播放（需静音，直点会被 autoplay 策略拦）' : '可播放')
    : (after.paused ? '点不动（检查 error 字段）' : '已解除暂停但时间不走（可能缓冲或源失效）');

  console.log('%c[自检] 结论：' + verdict, 'font-weight:bold;color:' + (advancing ? 'green' : 'crimson'));
  console.table([{
    结论: verdict,
    时间轴: `${t1}s -> ${t2}s（${advancing ? '在走' : '没走'}）`,
    是否需静音: ok(needMute),
    静音状态: ok(state().muted),
    readyState: state().readyState,
    错误: state().error
  }]);

  // 想让它停下就取消下面这行注释
  // if (player) player.pause(); else video.pause();
})();
