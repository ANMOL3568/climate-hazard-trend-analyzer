import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',workers:1,timeout:45000,use:{baseURL:'http://127.0.0.1:5173',channel:'msedge',headless:true},webServer:{command:'npm run dev',url:'http://127.0.0.1:5173',reuseExistingServer:true},reporter:[['list'],['json',{outputFile:'test-results/results.json'}]]});
