import { createTheme } from '@mui/material/styles';
import { palette } from './palette';

export const theme = createTheme({
  palette,
  typography: {
    fontFamily: '"Inter", sans-serif',
    h1: { fontSize: '28px', fontWeight: 700, lineHeight: 1.3 },
    h2: { fontSize: '24px', fontWeight: 600, lineHeight: 1.4 },
    h3: { fontSize: '20px', fontWeight: 600, lineHeight: 1.4 },
    body1: { fontSize: '16px', lineHeight: 1.5 },
    body2: { fontSize: '14px', lineHeight: 1.5 },
    caption: { fontSize: '12px', color: '#94A3B8' }
  },
  spacing: 8,
  shape: { borderRadius: 12 },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
          height: 40,
          borderRadius: 8,
        },
        containedPrimary: {
          backgroundColor: '#2563EB',
          '&:hover': { backgroundColor: '#1D4ED8' }
        }
      }
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundColor: '#FFFFFF',
          borderRadius: 12,
          boxShadow: '0px 2px 4px rgba(0,0,0,0.02), 0px 1px 2px rgba(0,0,0,0.03)',
        }
      }
    }
  }
});