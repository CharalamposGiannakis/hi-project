import { mount } from 'svelte';
import JsonViewer from './JsonViewer.svelte';
import './app.css';

const target = document.getElementById('app');
if (!target) throw new Error('Missing #app element');
mount(JsonViewer, { target });
