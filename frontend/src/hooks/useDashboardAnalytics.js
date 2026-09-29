import { useQuery } from '@tanstack/react-query';
import { getDashboardAnalytics } from '../api/dashboard';

export const useDashboardAnalytics = () => {
  return useQuery({
    queryKey: ['dashboardAnalytics'],
    queryFn: getDashboardAnalytics,
    refetchInterval: 30000,
  });
};