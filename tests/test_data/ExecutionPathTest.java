package testdata;

public class ExecutionPathTest {
    public int simpleMethod(int x) {
        if (x > 0) {
            return x * 2;
        } else {
            return x * 3;
        }
    }

    public void loopMethod(int n) {
        int sum = 0;
        for (int i = 0; i < n; i++) {
            sum += i;
        }
        System.out.println(sum);
    }

    public int switchMethod(int value) {
        switch (value) {
            case 1:
                return 10;
            case 2:
                return 20;
            default:
                return 0;
        }
    }
}