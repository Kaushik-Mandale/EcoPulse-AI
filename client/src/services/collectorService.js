import api from './api';

// The server derives the Collector's ward from the authenticated account.
export const fetchCollectorTasks = async () => (await api.get('/collector/tasks')).data;
