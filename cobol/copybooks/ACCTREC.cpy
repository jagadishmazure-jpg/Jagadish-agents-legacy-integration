      *> Account master record, 96 bytes. Harbor Ridge Savings (fictional).
       01  ACCT-REC.
           05  ACCT-ID             PIC X(10).
           05  ACCT-NAME           PIC X(30).
           05  ACCT-TYPE           PIC X(1).
           05  ACCT-BALANCE        PIC S9(9)V99 COMP-3.
           05  ACCT-OPEN-DATE      PIC 9(8).
           05  ACCT-STATUS         PIC X(1).
           05  ACCT-EMAIL          PIC X(40).
