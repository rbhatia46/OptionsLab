const assert=require('node:assert/strict');
const time=require('../app/options_lab/web/time.js');
assert.equal(time.shift('06:00',330),'11:30');
assert.equal(time.inputToUtc('17:00'),'11:30');
assert.equal(time.shift('12:00',330),'17:30');
assert.equal(time.timestamp('2026-06-01T22:45:00Z'),'2026-06-02 04:15:00 IST');
assert.throws(()=>time.inputToUtc('01:00'));
for(const clock of ['05:30','11:30','17:00','23:59'])assert.equal(time.shift(time.inputToUtc(clock),330),clock);
console.log('IST clock, date rollover and round-trip checks passed');
