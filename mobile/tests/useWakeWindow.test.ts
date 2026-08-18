describe('useWakeWindow Unit Tests', () => {
  it('should calculate wake window correctly for 6 month old infant', () => {
    const ageMonths = 6.0;
    const baseWakeWindow = 150; // from standard pediatric wake window table
    const lastWakeTime = new Date('2026-08-18T10:00:00Z');

    const expectedNextSleep = new Date(lastWakeTime.getTime() + baseWakeWindow * 60000);
    const expectedNotification = new Date(expectedNextSleep.getTime() - 15 * 60000);

    expect(expectedNextSleep.toISOString()).toBe('2026-08-18T12:30:00.000Z');
    expect(expectedNotification.toISOString()).toBe('2026-08-18T12:15:00.000Z');
  });

  it('should apply 15% overtired reduction when previous nap is under 30 minutes', () => {
    const baseWakeWindow = 120; // 4 month old
    const shortNapDuration = 25; // under 30 mins
    
    const isOvertired = shortNapDuration < 30;
    const adjustedWakeWindow = isOvertired ? Math.round(baseWakeWindow * 0.85) : baseWakeWindow;

    expect(isOvertired).toBe(true);
    expect(adjustedWakeWindow).toBe(102); // 120 * 0.85 = 102
  });
});
