async page => {
  const result = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const rec = buttons.find(b => /approve recommendation/i.test(b.getAttribute('aria-label') || ''));
    if (rec) { rec.click(); return { clicked: 'approve' }; }
    return { clicked: 'none' };
  });
  await page.waitForTimeout(800);
  return result;
}
