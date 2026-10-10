'use client';
import { useEffect, useState } from 'react';
import { API } from '@/lib/api';

export default function Home() {
  const [status, setStatus] = useState('loading...');

  useEffect(() => {
    fetch(`${API}/api/health`)
      .then((r) => r.json())
      .then((d) => setStatus(d.status))
      .catch(() => setStatus('backend not reachable'));
  }, []);

  return <main className='p-8 text-xl'>Backend says: {status}</main>;
}