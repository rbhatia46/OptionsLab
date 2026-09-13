// Browser inputs are IST; saved configurations and tick timestamps remain UTC.
const LabTime = (() => {
  function shift(clock, minutes) {
    if (!/^\d{2}:\d{2}$/.test(clock)) throw Error('Enter a valid HH:MM time.');
    const [h,m]=clock.split(':').map(Number);
    if(h>23||m>59)throw Error('Enter a valid HH:MM time.');
    const total=(h*60+m+minutes+1440)%1440;
    return `${String(Math.floor(total/60)).padStart(2,'0')}:${String(total%60).padStart(2,'0')}`;
  }
  function inputToUtc(clock) {
    if(clock<'05:30')throw Error('This intraday engine supports same-date IST sessions from 05:30 onward. Sessions before 05:30 IST require previous-day tick loading and are not supported yet.');
    return shift(clock,-330);
  }
  function timestamp(value) {
    if(!value)return '—';
    const date=new Date(value);
    if(!Number.isFinite(date.getTime()))return String(value);
    return new Date(date.getTime()+330*60000).toISOString().slice(0,19).replace('T',' ')+' IST';
  }
  function evidence(value) {
    if(Array.isArray(value))return value.map(evidence);
    if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,evidence(v)]));
    return typeof value==='string'&&/^\d{4}-\d{2}-\d{2}T.*(?:Z|\+00:00)$/.test(value)?timestamp(value):value;
  }
  return {shift,inputToUtc,timestamp,evidence};
})();
if(typeof module!=='undefined')module.exports=LabTime;
