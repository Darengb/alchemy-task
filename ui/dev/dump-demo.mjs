// Print the preview harness's demo data as JSON (dates relative to today in New York).
import { demoData } from './demo-data.js'

const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
const d = demoData(today)
process.stdout.write(JSON.stringify({ today, areas: d.areas, tasks: d.tasks }, null, 1))
