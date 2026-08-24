/**
 * The attendance history table, and the three things it got wrong.
 *
 * Seen in production: a shift clocked in at 11:14:04 and out at 11:14:09 -
 * five seconds, genuinely finished - showing "-" for hours; the Type and
 * Location columns reading "-" on every row for everyone; and shifts from
 * weeks earlier still offering a live "Clock Out" button.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { jsPDF } = require('jspdf');

const ROOT = path.resolve(__dirname, '..');

function boot() {
    const html = fs.readFileSync(path.join(ROOT, 'hr.html'), 'utf8')
        .replace(/<script[^>]*src=[^>]*><\/script>/g, '');
    const dom = new JSDOM(html, {
        runScripts: 'outside-only', pretendToBeVisual: true,
        url: 'https://localhost/hr.html',
    });
    const w = dom.window;
    w.jspdf = { jsPDF };
    w.Chart = function () { this.destroy = () => { }; this.update = () => { }; };
    w.Chart.defaults = { color: '', font: {}, plugins: {} };
    w.Chart.register = () => { };
    w.URL.createObjectURL = () => 'blob:stub';
    w.URL.revokeObjectURL = () => { };
    w.fetch = () => Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({}), text: () => Promise.resolve('{}'),
    });
    w.eval(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'));
    return w;
}

let failures = 0;
const check = (label, ok, detail) => {
    if (ok) console.log(`ok    ${label}`);
    else { failures++; console.log(`FAIL  ${label}${detail ? ': ' + detail : ''}`); }
};

const w = boot();
const cellsOf = (i) => [...w.document.querySelectorAll('#attendance-table-body tr')[i].cells]
    .map(c => c.textContent.trim());

w.renderAttendance([
    // finished, but so short it rounds to nothing
    { employee_id: 1, employee_name: 'A', date: '2026-08-24', clock_in: '11:14:04',
      clock_out: '11:14:09', total_hours: 0, status: 'completed',
      check_type: 'office', location_label: 'Head office' },
    // a normal finished shift
    { employee_id: 2, employee_name: 'B', date: '2026-08-09', clock_in: '15:31:43',
      clock_out: '15:33:06', total_hours: 0.02, status: 'completed',
      check_type: 'remote', location_label: 'Home' },
    // still at work
    { employee_id: 3, employee_name: 'C', date: '2026-08-24', clock_in: '09:00:00',
      clock_out: '', total_hours: 0, status: 'present',
      check_type: 'office', location_label: 'Head office' },
    // forgot to clock out, closed by the nightly job
    { employee_id: 4, employee_name: 'D', date: '2026-08-06', clock_in: '21:44:06',
      clock_out: '', total_hours: 0, status: 'needs_review',
      check_type: 'office', location_label: 'Head office' },
]);

const HOURS = 4, TYPE = 5, LOCATION = 6, ACTIONS = 8;

// --- a finished shift always shows a number, even when that number is nought
check('a five-second shift reads 0.00h, not a dash',
    cellsOf(0)[HOURS] === '0.00h', cellsOf(0)[HOURS]);
check('a normal shift still reads its hours',
    cellsOf(1)[HOURS] === '0.02h', cellsOf(1)[HOURS]);
check('a shift still running has no hours yet',
    cellsOf(2)[HOURS] === '-', cellsOf(2)[HOURS]);

// --- the two columns that were never sent
check('the type column shows the type',
    cellsOf(0)[TYPE] === 'office', cellsOf(0)[TYPE]);
check('and distinguishes remote from office',
    cellsOf(1)[TYPE] === 'remote', cellsOf(1)[TYPE]);
check('the location column shows the location',
    cellsOf(0)[LOCATION] === 'Head office', cellsOf(0)[LOCATION]);

// --- Clock Out belongs only to a shift that is actually open
check('somebody still at work can be clocked out',
    cellsOf(2)[ACTIONS].includes('Clock Out'), cellsOf(2)[ACTIONS] || '(empty)');
check('a finished shift cannot',
    !cellsOf(0)[ACTIONS].includes('Clock Out'), cellsOf(0)[ACTIONS]);
check('and neither can one the nightly job closed weeks ago',
    !cellsOf(3)[ACTIONS].includes('Clock Out'), cellsOf(3)[ACTIONS] || '(empty)');
check('which is shown as needing review',
    cellsOf(3)[7] === 'needs_review', cellsOf(3)[7]);

console.log(failures ? `\n${failures} failed` : '\nall good');
process.exit(failures ? 1 : 0);
