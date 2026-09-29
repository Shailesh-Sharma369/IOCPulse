import { axiosClient } from './axiosClient';

export const getDashboardMetrics = async () => {
  const response = await axiosClient.get('/api/v1/dashboard');
  return response.data.data;
};

export const getDashboardAnalytics = async () => {
  try {
    const response = await axiosClient.get('/api/v1/dashboard/analytics');
    return response.data.data;
  } catch (error) {
    // If endpoint is not yet implemented, return empty data to avoid crash
    console.warn('Dashboard analytics endpoint not available:', error);
    return {
      metrics: {},
      articles_by_source: [],
      ioc_distribution: {},
      iocs_this_month: 0,
      threat_summary: {},
      recent_activity: [],
      recent_articles: [],
    };
  }
};