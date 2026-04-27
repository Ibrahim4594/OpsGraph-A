async page => await page.evaluate(() => {
  const get = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const cs = getComputedStyle(el);
    return { color: cs.color, bg: cs.backgroundColor, font: cs.fontFamily, fontSize: cs.fontSize, fontWeight: cs.fontWeight };
  };
  return {
    body: get('body'),
    h1: get('h1'),
    muted: get('p'),
    sidebarLink: get('nav a[aria-current="page"]'),
    sloValue: get('[role="status"][aria-label="Availability SLO"] div')
  };
})
