/**
 * Chart utilities for FlaskReports
 * This file contains functions for creating and updating various charts used throughout the application
 */

// Configuration defaults for all charts
const defaultChartConfig = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
        labels: {
          boxWidth: 15,
          padding: 15,
          font: {
            family: "'Inter', sans-serif",
          }
        }
      },
      tooltip: {
        backgroundColor: 'rgba(30, 64, 175, 0.8)',
        titleFont: {
          family: "'Inter', sans-serif",
          size: 14,
          weight: 'bold'
        },
        bodyFont: {
          family: "'Inter', sans-serif",
          size: 13
        },
        padding: 10,
        cornerRadius: 4,
        displayColors: true
      }
    }
  };
  
  // Colors for charts
  const chartColors = {
    primary: '#1E40AF',
    primaryLight: 'rgba(30, 64, 175, 0.1)',
    teal: '#0D9488',
    tealLight: 'rgba(13, 148, 136, 0.1)',
    success: '#10B981',
    successLight: 'rgba(16, 185, 129, 0.1)',
    warning: '#F59E0B',
    warningLight: 'rgba(245, 158, 11, 0.1)',
    error: '#EF4444',
    errorLight: 'rgba(239, 68, 68, 0.1)',
    gray: '#6B7280',
    grayLight: 'rgba(107, 114, 128, 0.1)'
  };
  
  /**
   * Creates a bar chart for campaign data
   * @param {string} elementId - The ID of the canvas element
   * @param {Array} labels - Array of labels
   * @param {Array} data - Array of data values
   * @param {string} color - The color of the bars (from chartColors)
   * @param {string} title - The chart title
   */
  function createBarChart(elementId, labels, data, color, title) {
    const ctx = document.getElementById(elementId).getContext('2d');
    
    return new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: title,
          data: data,
          backgroundColor: chartColors[color] || chartColors.primary,
          borderColor: chartColors[color] || chartColors.primary,
          borderWidth: 1
        }]
      },
      options: {
        ...defaultChartConfig,
        scales: {
          y: {
            beginAtZero: true,
            grid: {
              drawBorder: false
            },
            ticks: {
              font: {
                family: "'Inter', sans-serif"
              }
            }
          },
          x: {
            grid: {
              display: false
            },
            ticks: {
              font: {
                family: "'Inter', sans-serif"
              }
            }
          }
        }
      }
    });
  }
  
  /**
   * Creates a horizontal bar chart (often used for campaigns by purchase/cost)
   * @param {string} elementId - The ID of the canvas element
   * @param {Array} labels - Array of labels
   * @param {Array} data - Array of data values
   * @param {string} color - The color of the bars (from chartColors)
   * @param {string} title - The chart title
   */
  function createHorizontalBarChart(elementId, labels, data, color, title) {
    const ctx = document.getElementById(elementId).getContext('2d');
    
    return new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: title,
          data: data,
          backgroundColor: chartColors[color] || chartColors.primary,
          borderColor: chartColors[color] || chartColors.primary,
          borderWidth: 1
        }]
      },
      options: {
        ...defaultChartConfig,
        indexAxis: 'y',
        scales: {
          x: {
            beginAtZero: true,
            grid: {
              drawBorder: false
            },
            ticks: {
              font: {
                family: "'Inter', sans-serif"
              }
            }
          },
          y: {
            grid: {
              display: false
            },
            ticks: {
              font: {
                family: "'Inter', sans-serif"
              }
            }
          }
        }
      }
    });
  }
  
  /**
   * Creates a line chart (often used for time series data)
   * @param {string} elementId - The ID of the canvas element
   * @param {Array} labels - Array of date/time labels
   * @param {Array} datasets - Array of dataset objects
   */
  function createLineChart(elementId, labels, datasets) {
    const ctx = document.getElementById(elementId).getContext('2d');
    
    // Process datasets to add styling
    const processedDatasets = datasets.map((dataset, index) => {
      const colors = Object.entries(chartColors).filter(([key]) => !key.includes('Light'));
      const colorKey = colors[index % colors.length][0];
      
      return {
        label: dataset.label,
        data: dataset.data,
        borderColor: chartColors[dataset.color] || chartColors[colorKey] || chartColors.primary,
        backgroundColor: chartColors[dataset.color + 'Light'] || chartColors[colorKey + 'Light'] || chartColors.primaryLight,
        tension: 0.4,
        fill: dataset.fill !== undefined ? dataset.fill : false,
        yAxisID: dataset.yAxisID || 'y'
      };
    });
    
    return new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: processedDatasets
      },
      options: {
        ...defaultChartConfig,
        scales: {
          y: {
            beginAtZero: true,
            grid: {
              drawBorder: false
            },
            ticks: {
              font: {
                family: "'Inter', sans-serif"
              }
            }
          },
          x: {
            grid: {
              display: false
            },
            ticks: {
              font: {
                family: "'Inter', sans-serif"
              }
            }
          }
        }
      }
    });
  }
  
  /**
   * Creates a doughnut/pie chart
   * @param {string} elementId - The ID of the canvas element
   * @param {Array} labels - Array of labels
   * @param {Array} data - Array of data values
   * @param {Array} colors - Array of colors (optional)
   */
  function createDoughnutChart(elementId, labels, data, colors = null) {
    const ctx = document.getElementById(elementId).getContext('2d');
    
    let backgroundColor;
    if (colors) {
      backgroundColor = colors.map(color => chartColors[color] || color);
    } else {
      backgroundColor = [
        chartColors.primary,
        chartColors.teal,
        chartColors.success,
        chartColors.warning,
        chartColors.error
      ];
    }
    
    return new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: data,
          backgroundColor: backgroundColor,
          borderWidth: 1
        }]
      },
      options: {
        ...defaultChartConfig,
        cutout: '70%'
      }
    });
  }
  
  // Export functions
  window.FlaskReportsCharts = {
    createBarChart,
    createHorizontalBarChart,
    createLineChart,
    createDoughnutChart,
    colors: chartColors
  };
