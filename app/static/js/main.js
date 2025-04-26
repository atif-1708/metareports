/**
 * Main JavaScript file for FlaskReports
 * Contains UI interactions, form handling, and other client-side functionality
 */

document.addEventListener('DOMContentLoaded', function() {
    // Mobile sidebar toggle
    const setupSidebar = () => {
      const sidebarToggle = document.getElementById('sidebar-toggle');
      const closeSidebar = document.getElementById('close-sidebar');
      const sidebarBackdrop = document.getElementById('sidebar-backdrop');
      const mobileSidebar = document.getElementById('mobile-sidebar');
      
      if (sidebarToggle && closeSidebar && sidebarBackdrop && mobileSidebar) {
        sidebarToggle.addEventListener('click', function() {
          mobileSidebar.style.display = 'flex';
          // Small delay to ensure display:flex is applied before adding the transition class
          setTimeout(() => {
            mobileSidebar.classList.add('sidebar-open');
          }, 10);
        });
        
        function closeMobileSidebar() {
          mobileSidebar.classList.remove('sidebar-open');
          // Wait for transition to complete before hiding
          setTimeout(() => {
            mobileSidebar.style.display = 'none';
          }, 300);
        }
        
        closeSidebar.addEventListener('click', closeMobileSidebar);
        sidebarBackdrop.addEventListener('click', closeMobileSidebar);
      }
    };
    
    // File upload preview
    const setupFileUpload = () => {
      const fileInput = document.getElementById('report_file');
      const fileNameDiv = document.getElementById('file-name');
      
      if (fileInput && fileNameDiv) {
        const fileNameSpan = fileNameDiv.querySelector('span');
        
        fileInput.addEventListener('change', function() {
          if (this.files && this.files.length > 0) {
            fileNameSpan.textContent = this.files[0].name;
            fileNameDiv.classList.remove('hidden');
          } else {
            fileNameDiv.classList.add('hidden');
          }
        });
      }
    };
    
    // Toggle between metrics on dashboard
    const setupMetricToggle = () => {
      const metricSelector = document.getElementById('topCampaignsMetric');
      const purchasesDiv = document.getElementById('topCampaignsByPurchases');
      const costDiv = document.getElementById('topCampaignsByCost');
      
      if (metricSelector && purchasesDiv && costDiv) {
        metricSelector.addEventListener('change', function() {
          if (this.value === 'purchases') {
            purchasesDiv.style.display = 'block';
            costDiv.style.display = 'none';
          } else {
            purchasesDiv.style.display = 'none';
            costDiv.style.display = 'block';
          }
        });
      }
    };
    
    // Form validation enhancements
    const setupFormValidation = () => {
      const forms = document.querySelectorAll('form');
      
      forms.forEach(form => {
        const requiredInputs = form.querySelectorAll('input[required], select[required], textarea[required]');
        
        requiredInputs.forEach(input => {
          // Add visual indicator for required fields
          const label = document.querySelector(`label[for="${input.id}"]`);
          if (label) {
            const requiredIndicator = document.createElement('span');
            requiredIndicator.textContent = ' *';
            requiredIndicator.className = 'text-red-500';
            label.appendChild(requiredIndicator);
          }
          
          // Real-time validation
          input.addEventListener('blur', function() {
            if (!this.value.trim()) {
              this.classList.add('border-red-500');
              
              // Add error message if not already present
              let errorDiv = this.parentElement.querySelector('.real-time-error');
              if (!errorDiv) {
                errorDiv = document.createElement('div');
                errorDiv.className = 'text-sm text-red-500 mt-1 real-time-error';
                errorDiv.textContent = 'This field is required';
                this.parentElement.appendChild(errorDiv);
              }
            } else {
              this.classList.remove('border-red-500');
              
              // Remove error message if present
              const errorDiv = this.parentElement.querySelector('.real-time-error');
              if (errorDiv) {
                errorDiv.remove();
              }
            }
          });
        });
      });
    };
    
    // CSV Template download
    const setupCSVTemplateDownload = () => {
      const downloadButton = document.querySelector('[onclick="downloadCSVTemplate(event)"]');
      
      if (downloadButton) {
        downloadButton.addEventListener('click', function(event) {
          event.preventDefault();
          
          const csvContent = "Campaign Name,Purchases,Cost Per Purchase\nSummer Sale Campaign,256,12.50\nNew Product Launch,128,24.75\nHoliday Promotion,312,18.99";
          
          const blob = new Blob([csvContent], { type: 'text/csv' });
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          
          a.setAttribute('href', url);
          a.setAttribute('download', 'campaign_report_template.csv');
          a.click();
          
          window.URL.revokeObjectURL(url);
        });
      }
    };
    
    // Notification auto-dismissal
    const setupNotifications = () => {
      const notifications = document.querySelectorAll('.notification');
      
      notifications.forEach(notification => {
        // Add dismiss button
        const dismissButton = document.createElement('button');
        dismissButton.innerHTML = '<i class="fas fa-times"></i>';
        dismissButton.className = 'ml-auto text-gray-400 hover:text-gray-600 focus:outline-none';
        dismissButton.addEventListener('click', () => {
          notification.remove();
        });
        
        notification.appendChild(dismissButton);
        
        // Auto-dismiss after 5 seconds for success notifications
        if (notification.classList.contains('notification-success')) {
          setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transition = 'opacity 0.5s ease';
            
            setTimeout(() => {
              notification.remove();
            }, 500);
          }, 5000);
        }
      });
    };
    
    // Initialize all UI components
    setupSidebar();
    setupFileUpload();
    setupMetricToggle();
    setupFormValidation();
    setupCSVTemplateDownload();
    setupNotifications();
    
    // Form confirmation dialogs
    const confirmForms = document.querySelectorAll('form[data-confirm]');
    confirmForms.forEach(form => {
      form.addEventListener('submit', function(event) {
        const message = this.getAttribute('data-confirm');
        if (!confirm(message)) {
          event.preventDefault();
        }
      });
    });
    
    // Print functionality
    const printButtons = document.querySelectorAll('.btn-print');
    printButtons.forEach(button => {
      button.addEventListener('click', function(event) {
        event.preventDefault();
        window.print();
      });
    });
  });
  
  // CSV Template download function (for direct HTML onclick attribute)
  function downloadCSVTemplate(event) {
    event.preventDefault();
    
    const csvContent = "Campaign Name,Purchases,Cost Per Purchase\nSummer Sale Campaign,256,12.50\nNew Product Launch,128,24.75\nHoliday Promotion,312,18.99";
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    
    a.setAttribute('href', url);
    a.setAttribute('download', 'campaign_report_template.csv');
    a.click();
    
    window.URL.revokeObjectURL(url);
  }
  
  // Format currency values
  function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'PKR',
      minimumFractionDigits: 2
    }).format(value);
  }
  
  // Format numbers with commas
  function formatNumber(value) {
    return new Intl.NumberFormat('en-US').format(value);
  }