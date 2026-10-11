import {test,expect} from '@playwright/test';
import {annualCsv,csvCell,dailyForYear,validateAnalysis} from '../src/analysis-utils';
import fs from 'node:fs';
import path from 'node:path';
import {spawn,ChildProcess} from 'node:child_process';
import {project,unproject} from '../src/RegionMap';

test('map projection preserves coordinates and wraps longitude',()=>{
 for(const [lat,lon] of [[28.614,77.209],[19.07283,72.88261],[-45,-179],[0,179]]){
  const point=project(lat,lon,5);const restored=unproject(point.x,point.y,5);
  expect(restored.latitude).toBeCloseTo(lat,5);expect(restored.longitude).toBeCloseTo(lon,5);
 }
 expect(unproject(256*4,0,1).longitude).toBe(-180);
 expect(unproject(0,-99999,1).latitude).toBeLessThanOrEqual(85.05112878);
});

test('CSV contract, escaping, empty exports and year filter',()=>{
 const annual=Array.from({length:32},(_,i)=>({year:1990+i,events:i%3,days:i,coverage:100,rollingDays:i/2}));
 const csv=annualCsv(annual);const rows=csv.trim().split('\r\n');
 expect(rows).toHaveLength(33);
 for(let i=0;i<32;i++)expect(rows[i+1].split(',').map(Number)).toEqual([annual[i].year,annual[i].events,annual[i].days,annual[i].coverage,annual[i].rollingDays]);
 expect(annualCsv([]).trim().split('\r\n')).toHaveLength(1);
 expect(csvCell('a,"b"\nc')).toBe('"a,""b""\nc"');
 expect(dailyForYear([{date:'2020-01-01'},{date:'2021-01-01'}],2021)).toEqual([{date:'2021-01-01'}]);
 expect(validateAnalysis(91,0,2000,2020)).toContain('valid coordinates');
 expect(validateAnalysis(0,0,2021,2020)).toContain('Start year');
});

const mumbai={id:1275339,name:'Mumbai',admin1:'Maharashtra',country:'India',latitude:19.07283,longitude:72.88261,label:'Mumbai, Maharashtra, India',kind:'Place reference point'};
const fixture={region:{latitude:19.073,longitude:72.883,start_year:2020,end_year:2021},threshold:33.4,baseline:[1981,2010],source:'Open-Meteo / ERA5',cached:false,summary:{events:1,days:3,longest:3,coverage:100,slope:0},annual:[{year:2020,events:1,days:3,coverage:100,rollingDays:3},{year:2021,events:0,days:0,coverage:100,rollingDays:1.5}],daily:[{date:'2020-01-01',temperature:35},{date:'2020-01-02',temperature:36},{date:'2020-01-03',temperature:34},{date:'2021-01-01',temperature:25},{date:'2021-01-02',temperature:26},{date:'2021-01-03',temperature:27}],events:[{start:'2020-01-01',end:'2020-01-03',duration:3,peak:36}]};

test('Mumbai selection, result consistency, chart filter, CSV download, failure and recovery',async({page})=>{
 await page.route('**/api/regions?*',route=>route.fulfill({json:[mumbai]}));
 let fail=false;
 await page.route('**/api/analyze',async route=>{
  if(fail){await route.abort('connectionrefused');return;}
  const body=route.request().postDataJSON();expect(body.latitude).toBe(mumbai.latitude);expect(body.longitude).toBe(mumbai.longitude);
  await route.fulfill({json:fixture});
 });
 await page.goto('/#/explorer');
 await page.getByPlaceholder('Search city or state').fill('Mumbai');
 await expect(page.locator('.coordinate')).toContainText('New Delhi');
 await page.getByRole('button',{name:/Mumbai, Maharashtra, India/}).click();
 await expect(page.locator('.coordinate')).toContainText(mumbai.label);
 await expect(page.getByLabel('Latitude')).toHaveValue('19.07283');
 await page.getByRole('button',{name:'Run analysis',exact:true}).click();
 await expect(page.locator('.section-title')).toContainText(mumbai.label);
 await expect(page.locator('.insight-foot')).toContainText('33.4');
 await expect(page.locator('.stat strong')).toHaveText(['1','3','3','100%']);
 await expect(page.locator('#event-register')).toContainText('2020-01-03');
 await expect(page.locator('.baseline-chip')).toContainText('1981–2010');
 await page.locator('.temperature').scrollIntoViewIfNeeded();
 const before=await page.locator('.temperature .recharts-area-area').getAttribute('d');
 await page.getByLabel('Temperature chart year').selectOption('2020');
 await page.waitForTimeout(700);
 expect(await page.locator('.temperature .recharts-area-area').getAttribute('d')).not.toBe(before);
 const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Export yearly CSV'}).click();const download=await pending;
 const file=await download.path();expect(fs.readFileSync(file!,'utf8')).toBe(annualCsv(fixture.annual));
 fail=true;await page.getByRole('button',{name:'Run analysis',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Cannot reach the backend');
 await expect(page.getByRole('button',{name:'Run analysis',exact:true})).toBeEnabled();
 fail=false;await page.getByRole('button',{name:'Run analysis',exact:true}).click();await expect(page.locator('.stat strong').first()).toHaveText('1');
});

test('invalid filters and no matches',async({page})=>{
 await page.route('**/api/regions?*',route=>route.fulfill({json:[]}));
 await page.goto('/#/explorer');
 const years=page.locator('.controls input[type=number]');
 await years.nth(0).fill('2025');await years.nth(1).fill('2020');await page.getByRole('button',{name:'Run analysis',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Start year');
 await years.nth(0).fill('1939');await page.getByRole('button',{name:'Run analysis',exact:true}).click();await expect(page.getByRole('alert')).toContainText('1940');
 await years.nth(0).fill('2020');await page.getByLabel('Latitude').fill('91');await page.getByRole('button',{name:'Run analysis',exact:true}).click();await expect(page.getByRole('alert')).toContainText('valid coordinates');
 await page.getByPlaceholder('Search city or state').fill('unknown');await expect(page.getByRole('alert')).toContainText('No locations found');
});

test('390px home and populated explorer have no page overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto('/#/');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/home-390.png',fullPage:true});
 await page.getByRole('link',{name:'Open Dashboard',exact:true}).click();
 await page.route('**/api/analyze',route=>route.fulfill({json:fixture}));
 await page.getByLabel('Latitude').fill('19.07283');await page.getByLabel('Longitude').fill('72.88261');
 const mobileYears=page.locator('.controls input[type=number]');await mobileYears.nth(0).fill('2020');await mobileYears.nth(1).fill('2021');
 await page.getByRole('button',{name:'Run analysis',exact:true}).click();await expect(page.locator('.stat strong').first()).toHaveText('1');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await expect(page.locator('.charts .recharts-bar-rectangle').first()).toBeAttached();
 await page.waitForTimeout(1800); // Let Recharts' initial animation finish before visual QA.
 await page.screenshot({path:'test-results/explorer-390.png',fullPage:true});
 const controls=await page.locator('.controls input,.controls select,.controls .primary').all();
 for(const control of controls){const box=await control.boundingBox();expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.x+box!.width).toBeLessThanOrEqual(390);}
});


test('live 1990-2021 CSV matches backend annual metrics',async({page})=>{
 for(const name of ['delhi','mumbai']){
  const file=`../verification/${name}.json`;
  test.skip(!fs.existsSync(file),'Run Backend/verify_live.py first');
  const result=JSON.parse(fs.readFileSync(file,'utf8'));
  await page.route('**/api/analyze',route=>route.fulfill({json:result}));
  await page.goto('/#/explorer');
  await page.getByRole('button',{name:'Run analysis',exact:true}).click();
  await expect(page.locator('.stat strong').first()).toHaveText(String(result.summary.events));
  const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Export yearly CSV'}).click();const download=await pending;
  const csv=fs.readFileSync((await download.path())!,'utf8');
  const rows=csv.trim().split('\r\n').slice(1).map(line=>line.split(',').map(Number));
  expect(rows).toHaveLength(32);
  expect(rows.reduce((sum,row)=>sum+row[1],0)).toBe(result.summary.events);
  expect(rows.reduce((sum,row)=>sum+row[2],0)).toBe(result.summary.days);
  expect(csv).toBe(annualCsv(result.annual));
  fs.writeFileSync(`../verification/${name}-1990-2021.csv`,csv);
  await page.unroute('**/api/analyze');
 }
});

test('zero-event result remains usable',async({page})=>{
 await page.route('**/api/analyze',route=>route.fulfill({json:{...fixture,events:[],summary:{events:0,days:0,longest:0,coverage:100,slope:null}}}));
 await page.goto('/#/explorer');await page.getByRole('button',{name:'Run analysis',exact:true}).click();
 await expect(page.locator('#event-register')).toContainText('No heatwaves detected');
 await expect(page.getByRole('button',{name:'Export yearly CSV'})).toBeEnabled();
});

test('actual backend stop and restart recovers without stuck loading',async({page,request})=>{
 test.setTimeout(90000);
 let backend:ChildProcess|undefined;
 async function startBackend(){
  backend=spawn(path.resolve('../.venv/Scripts/python.exe'),['-m','uvicorn','main:app','--host','127.0.0.1','--port','8011'],{cwd:path.resolve('../Backend'),stdio:'ignore',windowsHide:true});
  for(let i=0;i<40;i++){
   try{const health=await request.get('http://127.0.0.1:8011/api/health',{timeout:1000});if(health.ok()){expect((await health.json()).database).toBe(true);return;}}catch{}
   await new Promise(resolve=>setTimeout(resolve,250));
  }
  throw new Error('Verification backend did not start');
 }
 async function stopBackend(){if(backend&&backend.exitCode===null){const stopped=new Promise(resolve=>backend!.once('exit',resolve));backend.kill();await stopped;}}
 try{
  await startBackend();
  await page.route('**/api/analyze',async route=>{try{const response=await route.fetch({url:'http://127.0.0.1:8011/api/analyze',timeout:10000,maxRetries:0});await route.fulfill({response});}catch{await route.abort('connectionrefused');}});
  await page.goto('/#/explorer');
  await page.getByLabel('Latitude').fill('19.07283');await page.getByLabel('Longitude').fill('72.88261');
  const years=page.locator('.controls input[type=number]');await years.nth(0).fill('2020');await years.nth(1).fill('2021');
  await page.getByRole('button',{name:'Run analysis',exact:true}).click();await expect(page.locator('.stat strong').first()).toHaveText('7');
  await stopBackend();
  await page.getByRole('button',{name:'Run analysis',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Cannot reach the backend');await expect(page.getByRole('button',{name:'Run analysis',exact:true})).toBeEnabled();
  await startBackend();
  await page.getByRole('button',{name:'Run analysis',exact:true}).click();await expect(page.locator('.stat strong').first()).toHaveText('7');await expect(page.locator('.section-title')).toContainText('Cached analysis');
 }finally{await stopBackend();}
});

test('ambiguous Bihar records retain full identity and do not auto-select',async({page})=>{
 const records=[{...mumbai,id:10470188,name:'Bihar',admin1:'Uttar Pradesh',label:'Bihar, Uttar Pradesh, India',latitude:27.29201,longitude:79.32543},{...mumbai,id:1208752,name:'Bihar',admin1:'Rajshahi Division',country:'Bangladesh',label:'Bihar, Rajshahi Division, Bangladesh',latitude:24.38925,longitude:89.00065}];
 await page.route('**/api/regions?*',route=>route.fulfill({json:records}));
 await page.goto('/#/explorer');await page.getByPlaceholder('Search city or state').fill('Bihar');
 await expect(page.locator('.places button')).toHaveCount(2);
 await expect(page.locator('.coordinate')).toContainText('New Delhi');
 await expect(page.locator('.places')).toContainText('27.29201, 79.32543');
 await page.getByRole('button',{name:/Bihar, Uttar Pradesh, India/}).click();
 await expect(page.locator('.coordinate')).toContainText('Bihar, Uttar Pradesh, India');
 await expect(page.getByLabel('Latitude')).toHaveValue('27.29201');await expect(page.getByLabel('Longitude')).toHaveValue('79.32543');
 await expect(page.locator('.scope-note')).toContainText('not a whole-state or area average');
});

test('upstream errors and non-JSON responses exit loading',async({page})=>{
 let badJson=false;
 await page.route('**/api/analyze',route=>badJson?route.fulfill({status:502,contentType:'text/html',body:'Bad gateway'}):route.fulfill({status:502,json:{detail:'Historical weather service unavailable. Please retry.'}}));
 await page.goto('/#/explorer');await page.getByRole('button',{name:'Run analysis',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Historical weather service unavailable');await expect(page.getByRole('button',{name:'Run analysis',exact:true})).toBeEnabled();
 badJson=true;await page.getByRole('button',{name:'Run analysis',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Request failed (502)');await expect(page.getByRole('button',{name:'Run analysis',exact:true})).toBeEnabled();
});

test('sidebar opens separate pages, preserves analysis and downloads reports',async({page})=>{
 await page.route('**/api/analyze',route=>route.fulfill({json:fixture}));
 await page.goto('/#/explorer');
 const nav=page.getByRole('navigation',{name:'Workspace navigation'});
 await nav.getByRole('link',{name:'Data Explorer',exact:true}).click();
 await expect(page).toHaveURL(/#\/data$/);await expect(page.getByText('No analysis available yet')).toBeVisible();
 await nav.getByRole('link',{name:'Analyze',exact:true}).click();
 await expect(page).toHaveURL(/#\/analyze$/);await expect(page.getByRole('heading',{name:'Analyze',exact:true})).toBeVisible();
 await expect(page.locator('.charts')).toHaveCount(0);
 await page.getByRole('button',{name:'Run analysis',exact:true}).click();await expect(page.getByText('Your analysis is ready')).toBeVisible();
 await page.getByRole('link',{name:'View dashboard'}).click();await expect(page.locator('.stat strong').first()).toHaveText('1');
 await nav.getByRole('link',{name:'Data Explorer',exact:true}).click();
 await expect(page.getByRole('tab',{name:'Annual summaries'})).toHaveAttribute('aria-selected','true');
 await page.getByLabel('Data explorer year').selectOption('2020');await expect(page.locator('tbody tr')).toHaveCount(1);
 await page.getByRole('tab',{name:'Heatwave events'}).click();await expect(page.locator('tbody')).toContainText('2020-01-03');
 await page.getByRole('tab',{name:'Daily temperatures'}).click();await expect(page.locator('tbody tr')).toHaveCount(3);
 await nav.getByRole('link',{name:'Export Reports',exact:true}).click();await expect(page).toHaveURL(/#\/reports$/);
 for(const name of ['Download annual CSV','Download event CSV','Download analysis JSON']){
  const pending=page.waitForEvent('download');await page.getByRole('button',{name,exact:true}).click();const download=await pending;
  const content=fs.readFileSync((await download.path())!,'utf8');
  if(name==='Download annual CSV')expect(content).toBe(annualCsv(fixture.annual));
  if(name==='Download event CSV')expect(content).toContain('2020-01-01,2020-01-03,3,36');
  if(name==='Download analysis JSON')expect(JSON.parse(content).summary).toEqual(fixture.summary);
 }
 await nav.getByRole('link',{name:'About',exact:true}).click();await expect(page).toHaveURL(/#\/about$/);await expect(page.getByRole('heading',{name:'Heatwave definition'})).toBeVisible();
 await page.goBack();await expect(page).toHaveURL(/#\/reports$/);
 await nav.getByRole('link',{name:'Dashboard',exact:true}).click();await expect(page.locator('.stat strong').first()).toHaveText('1');
 await expect(nav.getByRole('link',{name:'Dashboard',exact:true})).toHaveAttribute('aria-current','page');
});

test('mobile sidebar opens, navigates and closes without overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/#/explorer');
 await page.getByRole('button',{name:'Open navigation'}).click();
 await expect(page.locator('#workspace-sidebar')).toBeVisible();
 await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('link',{name:'Export Reports',exact:true}).click();
 await expect(page).toHaveURL(/#\/reports$/);await expect(page.locator('#workspace-sidebar')).not.toBeVisible();
 await expect(page.getByRole('button',{name:'Open navigation'})).toHaveAttribute('aria-expanded','false');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.getByRole('button',{name:'Open navigation'}).click();await page.getByRole('button',{name:'Close menu',exact:true}).click();
 await expect(page.locator('#workspace-sidebar')).not.toBeVisible();
});

test('map selection syncs coordinates, search, analysis and mobile layout',async({page})=>{
 await page.route('https://tile.openstreetmap.org/**',route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#eee"/></svg>'}));
 await page.route('**/api/regions?*',route=>route.fulfill({json:[mumbai]}));
 let submitted:any;
 await page.route('**/api/analyze',route=>{submitted=route.request().postDataJSON();return route.fulfill({json:fixture});});
 await page.goto('/#/explorer');await page.getByRole('button',{name:'Select on map',exact:true}).click();
 const map=page.getByRole('application',{name:'Region selection map'});
 await expect(map).toBeVisible();await expect(page.getByRole('link',{name:'© OpenStreetMap contributors'})).toBeVisible();
 await map.click({position:{x:180,y:120}});
 await expect(page.locator('.coordinate')).toContainText('Map-selected point');
 const lat=Number(await page.getByLabel('Latitude',{exact:true}).inputValue());const lon=Number(await page.getByLabel('Longitude',{exact:true}).inputValue());
 expect(lat).toBeGreaterThan(-86);expect(lat).toBeLessThan(86);expect(lon).not.toBe(77.209);
 await page.getByRole('button',{name:'Run analysis',exact:true}).click();await expect.poll(()=>submitted?.latitude).toBe(lat);expect(submitted.longitude).toBe(lon);
 await page.getByRole('button',{name:'Zoom in',exact:true}).click();await expect(page.locator('.map-toolbar')).toContainText('6');
 await map.focus();await map.press('ArrowRight');await map.press('Enter');
 expect(Number(await page.getByLabel('Longitude',{exact:true}).inputValue())).not.toBe(lon);
 await page.getByPlaceholder('Search city or state').fill('Mumbai');await page.getByRole('button',{name:/Mumbai, Maharashtra, India/}).click();
 await expect(page.getByLabel('Latitude',{exact:true})).toHaveValue('19.07283');
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/map-mobile.png',fullPage:true});
 await page.getByRole('button',{name:'Hide map',exact:true}).click();await expect(map).toHaveCount(0);
});

test('map country and state selection preserves identity and restricts search',async({page})=>{
 await page.route('https://tile.openstreetmap.org/**',route=>route.abort());
 await page.route('**/api/map-regions?*',route=>{
  const url=new URL(route.request().url());const state=url.searchParams.get('kind')==='state';
  if(state)expect(url.searchParams.get('country')).toBe('in');
  return route.fulfill({json:[{name:state?'Bihar':'India',label:state?'Bihar, India':'India',country:'India',country_code:'in',admin1:state?'Bihar':undefined,latitude:state?25.7:22,longitude:state?85.4:79,bounds:state?[24,28,83,89]:[6,36,68,98]}]});
 });
 await page.goto('/#/analyze');await page.getByRole('button',{name:'Select on map',exact:true}).click();
 await page.getByLabel('Map region name').fill('India');await page.getByRole('button',{name:'Find region',exact:true}).click();
 await page.locator('.map-region-results button').click();await expect(page.getByLabel('Map region level')).toHaveValue('state');
 await expect(page.locator('.map-country-chip')).toContainText('India');
 await page.getByLabel('Map region name').fill('Bihar');await page.getByRole('button',{name:'Find region',exact:true}).click();
 await page.locator('.map-region-results button').click();await expect(page.locator('.coordinate')).toContainText('Bihar, India');
 await expect(page.getByLabel('Latitude',{exact:true})).toHaveValue('25.7');await expect(page.getByLabel('Longitude',{exact:true})).toHaveValue('85.4');
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.getByRole('button',{name:'Change country',exact:true}).click();await expect(page.getByLabel('Map region level')).toHaveValue('country');
});

test('map tile failure keeps coordinate selection usable',async({page})=>{
 await page.route('https://tile.openstreetmap.org/**',route=>route.abort());
 await page.goto('/#/analyze');await page.getByRole('button',{name:'Select on map',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('Map tiles could not load');
 await page.getByRole('application',{name:'Region selection map'}).click({position:{x:120,y:120}});
 await expect(page.locator('.coordinate')).toContainText('Map-selected point');
 await expect(page.getByRole('button',{name:'Run analysis',exact:true})).toBeEnabled();
});

test('HeatWave theme, walkthrough and desktop/mobile layout',async({page})=>{
 await page.setViewportSize({width:1440,height:960});await page.goto('/#/');
 await expect(page.getByRole('heading',{name:'Understand Heatwave Trends Over Time'})).toBeVisible();
 await expect(page.locator('.heatwave-brand').first()).toContainText('HeatWave');
 await page.getByRole('button',{name:'Watch Demo'}).click();
 await expect(page.getByRole('dialog')).toBeVisible();await expect(page.getByRole('heading',{name:'Select your location'})).toBeVisible();
 for(let i=0;i<3;i++)await page.getByRole('button',{name:'Next',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Explore and export'})).toBeVisible();
 await page.getByRole('link',{name:'Start analysis',exact:true}).click();await expect(page).toHaveURL(/#\/analyze$/);
 await page.goto('/#/');await page.locator('.landing-hero').evaluate(async element=>{const image=new Image();image.src='/heatwave-city-hero.png';await image.decode();});
 await page.screenshot({path:'test-results/heatwave-home-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/heatwave-home-mobile.png',fullPage:true});
});


test('drought and heavy rainfall update analysis payload, units and CSV',async({page})=>{
 await page.route('**/api/analyze',route=>{
  const hazard=route.request().postDataJSON().hazard;
  expect(['drought','heavy_rainfall']).toContain(hazard);
  return route.fulfill({json:{...fixture,hazard,unit:'mm',definition:hazard==='drought'?'Dry-spell proxy: 15+ consecutive days below 1 mm':'Wet-day 95th percentile',baseline:hazard==='drought'?[]:[1981,2010],threshold:hazard==='drought'?1:50,daily:fixture.daily.map(r=>({date:r.date,precipitation:12})),events:[{start:'2020-01-01',end:'2020-01-03',duration:3,peak:60}]}});
 });
 await page.goto('/#/explorer');
 for(const hazard of ['drought','heavy_rainfall']){
  await page.getByLabel('Hazard type').selectOption(hazard);
  await expect(page.locator('.stat strong').first()).toHaveText('?');
  await page.getByRole('button',{name:'Run analysis',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Precipitation in context'})).toBeVisible();
  await expect(page.locator('#event-register')).toContainText('60 mm');
  const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Export yearly CSV'}).click();
  const download=await pending;expect(download.suggestedFilename()).toBe(hazard+'-annual-analysis.csv');
  expect(fs.readFileSync((await download.path())!,'utf8')).toContain(hazard+'_events,'+hazard+'_days');
 }
});
