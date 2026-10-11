export type AnnualRow = {year:number;events:number;days:number;coverage:number;rollingDays:number};
export function csvCell(value:unknown):string {
 const text = value == null ? '' : String(value);
 return /[",\r\n]/.test(text) ? '"'+text.replaceAll('"','""')+'"' : text;
}
export function annualCsv(rows:AnnualRow[], hazard='heatwave'):string {
 return [['year',`${hazard}_events`,`${hazard}_days`,'coverage_percent','rolling_average_days'], ...rows.map(r=>[r.year,r.events,r.days,r.coverage,r.rollingDays])].map(row=>row.map(csvCell).join(',')).join('\r\n')+'\r\n';
}
export function dailyForYear<T extends {date:string}>(daily:T[], year:number):T[]{return daily.filter(r=>r.date.startsWith(`${year}-`));}
export function locationLabel(p:{name:string;admin1?:string;country?:string;label?:string}):string {
 return p.label || [...new Set([p.name,p.admin1,p.country].filter(Boolean))].join(', ');
}
export function validateAnalysis(latitude:number, longitude:number, start:number, end:number):string|null {
 if(!Number.isFinite(latitude)||!Number.isFinite(longitude)||Math.abs(latitude)>90||Math.abs(longitude)>180)return 'Enter valid coordinates: latitude -90 to 90, longitude -180 to 180.';
 if(!Number.isInteger(start)||!Number.isInteger(end))return 'Enter whole calendar years.';
 if(start>end)return 'Start year must be less than or equal to end year.';
 if(start<1940||end>=new Date().getFullYear())return `Choose complete years from 1940 through ${new Date().getFullYear()-1}.`;
 if(end-start>59)return 'Select at most 60 years.';
 return null;
}
